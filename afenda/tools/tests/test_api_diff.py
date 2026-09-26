"""Tests for the OpenAPI change checker and version gate.

Most fixtures are built in code: neither the committed OpenAPI documents nor
`api_version.py` exist yet (other tasks in the same plan produce them), so
most of this file never reads the real tree. `BaseRefTests` is the one
exception, a git-backed test in this checkout's own history, the way
test_brand_images.py's `test_every_listed_path_exists_and_is_actually_recoloured`
reads real git blobs rather than fixtures.
"""
import contextlib
import io
import json
import unittest

from afenda.tools.api_diff import (
    Changes,
    ContractSummary,
    base_contract,
    base_ref_exists,
    changelog_section,
    check,
    diff,
    format_changes_report,
    load_set,
    main,
    render_changelog,
    required_bump,
)


def _world(paths=None, schemas=None):
    return {"paths": paths or {}, "schemas": schemas or {}}


def _op(request_props=None, request_required=None, description=None):
    body = {"type": "object", "properties": request_props or {}}
    if request_required:
        body["required"] = request_required
    post = {
        "operationId": "res.partner.write",
        "requestBody": {"required": True, "content": {"application/json": {"schema": body}}},
        "responses": {"200": {"description": "Success."}},
    }
    if description:
        post["description"] = description
    return {"post": post}


class ChangeClassTests(unittest.TestCase):
    """One test per Global Constraints change class (gc-change-gate.md)."""

    def test_removed_operation_is_breaking(self):
        base = _world(paths={"/json/2/res.partner/write": _op()})
        head = _world(paths={})
        changes = diff(base, head)
        self.assertTrue(
            any("removed operation" in c and "/json/2/res.partner/write" in c for c in changes.breaking),
            changes.breaking,
        )
        self.assertEqual(changes.additive, [])
        self.assertEqual(changes.descriptive, [])

    def test_removed_schema_property_is_breaking(self):
        base = _world(schemas={
            "res.partner": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "active": {"type": "boolean"}},
            }
        })
        head = _world(schemas={
            "res.partner": {"type": "object", "properties": {"name": {"type": "string"}}}
        })
        changes = diff(base, head)
        self.assertTrue(any("active" in c for c in changes.breaking), changes.breaking)

    def test_changed_property_type_is_breaking(self):
        base = _world(schemas={
            "res.partner": {"type": "object", "properties": {"age": {"type": "integer"}}}
        })
        head = _world(schemas={
            "res.partner": {"type": "object", "properties": {"age": {"type": "string"}}}
        })
        changes = diff(base, head)
        self.assertTrue(any("age" in c and "type" in c for c in changes.breaking), changes.breaking)

    def test_removed_enum_value_is_breaking(self):
        base = _world(schemas={
            "res.partner": {
                "type": "object",
                "properties": {"state": {"type": "string", "enum": ["draft", "done"]}},
            }
        })
        head = _world(schemas={
            "res.partner": {
                "type": "object",
                "properties": {"state": {"type": "string", "enum": ["draft"]}},
            }
        })
        changes = diff(base, head)
        self.assertTrue(any("done" in c for c in changes.breaking), changes.breaking)

    def test_newly_required_property_is_breaking(self):
        base = _world(schemas={
            "res.partner": {"type": "object", "properties": {"name": {"type": "string"}}}
        })
        head = _world(schemas={
            "res.partner": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            }
        })
        changes = diff(base, head)
        self.assertTrue(any("name" in c and "required" in c for c in changes.breaking), changes.breaking)

    def test_added_property_is_additive(self):
        base = _world(schemas={"res.partner": {"type": "object", "properties": {}}})
        head = _world(schemas={
            "res.partner": {"type": "object", "properties": {"nickname": {"type": "string"}}}
        })
        changes = diff(base, head)
        self.assertTrue(any("nickname" in c for c in changes.additive), changes.additive)
        self.assertEqual(changes.breaking, [])

    def test_description_change_is_descriptive(self):
        base = _world(paths={"/json/2/res.partner/write": _op(description="Old.")})
        head = _world(paths={"/json/2/res.partner/write": _op(description="New.")})
        changes = diff(base, head)
        self.assertTrue(
            any("/json/2/res.partner/write" in c for c in changes.descriptive), changes.descriptive
        )
        self.assertEqual(changes.breaking, [])
        self.assertEqual(changes.additive, [])

    def test_schema_level_title_change_is_descriptive(self):
        base = _world(schemas={
            "res.partner": {"type": "object", "title": "Contact", "properties": {}}
        })
        head = _world(schemas={
            "res.partner": {"type": "object", "title": "Contact record", "properties": {}}
        })
        changes = diff(base, head)
        self.assertTrue(
            any("res.partner" in c and "title" in c for c in changes.descriptive), changes.descriptive
        )
        self.assertEqual(changes.breaking, [])
        self.assertEqual(changes.additive, [])


class UnionAndResolutionTests(unittest.TestCase):
    def test_model_moving_between_area_files_is_no_change(self):
        model_schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        base_docs = {
            "sales.json": json.dumps({
                "paths": {},
                "components": {"schemas": {"sale.order": model_schema}},
            }),
        }
        head_docs = {
            "core.json": json.dumps({
                "paths": {},
                "components": {"schemas": {"sale.order": model_schema}},
            }),
        }
        base = load_set(base_docs.get, list(base_docs))
        head = load_set(head_docs.get, list(head_docs))
        changes = diff(base, head)
        self.assertEqual(changes.breaking, [])
        self.assertEqual(changes.additive, [])
        self.assertEqual(changes.descriptive, [])

    def test_newly_required_parameter_inside_a_shared_body_is_breaking(self):
        shared_paths = {
            "/json/2/res.partner/write": {
                "post": {
                    "operationId": "res.partner.write",
                    "requestBody": {"$ref": "#/components/requestBodies/write"},
                    "responses": {"200": {"description": "Success."}},
                }
            },
            "/json/2/res.users/write": {
                "post": {
                    "operationId": "res.users.write",
                    "requestBody": {"$ref": "#/components/requestBodies/write"},
                    "responses": {"200": {"description": "Success."}},
                }
            },
        }
        base_doc = {
            "paths": shared_paths,
            "components": {
                "schemas": {},
                "requestBodies": {
                    "write": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "properties": {"vals": {"type": "object"}}}
                            }
                        },
                    }
                },
            },
        }
        head_doc = {
            "paths": shared_paths,
            "components": {
                "schemas": {},
                "requestBodies": {
                    "write": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"vals": {"type": "object"}},
                                    "required": ["vals"],
                                }
                            }
                        },
                    }
                },
            },
        }
        base = load_set({"core.json": json.dumps(base_doc)}.get, ["core.json"])
        head = load_set({"core.json": json.dumps(head_doc)}.get, ["core.json"])
        changes = diff(base, head)
        self.assertTrue(
            any("vals" in c and "required" in c for c in changes.breaking), changes.breaking
        )

    def test_info_changes_are_ignored(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        base_doc = {"info": {"version": "1"}, "paths": {}, "components": {"schemas": {"res.partner": schema}}}
        head_doc = {"info": {"version": "2"}, "paths": {}, "components": {"schemas": {"res.partner": schema}}}
        base = load_set({"core.json": json.dumps(base_doc)}.get, ["core.json"])
        head = load_set({"core.json": json.dumps(head_doc)}.get, ["core.json"])
        changes = diff(base, head)
        self.assertEqual((changes.breaking, changes.additive, changes.descriptive), ([], [], []))


class BaseContractTests(unittest.TestCase):
    """`base_contract` is the one "no base contract" rule shared by `check`
    and `changelog` (gc-change-gate.md: either ASSET_DIR or api_version.py
    absent means no base contract)."""

    def test_documents_without_version_file_is_no_base_contract(self):
        # Base has JSON documents (`list_base` would return names) but no
        # api_version.py at that ref (`get_text_at_ref` for VERSION_FILE
        # returns None) -- still no base contract, not "1.0.0".
        names, base_version = base_contract(["core.json"], None)
        self.assertEqual(names, ["core.json"])
        self.assertIsNone(base_version)

        # The consequence is the same as a fully absent base: `check` skips
        # the bump rule entirely...
        changes = Changes(breaking=["removed operation x"], additive=[], descriptive=[])
        changelog = "# API changelog\n\n## 1.0.0 — initial contract\n"
        self.assertEqual(check(base_version, "1.0.0", changes, changelog), [])

        # ...and `changelog` writes the "initial contract" heading.
        section = render_changelog(None, "1.0.0", changes, first=base_version is None)
        self.assertIn("initial contract", section)


class BaseRefTests(unittest.TestCase):
    """`base_ref_exists` (and the `check`/`changelog` CLI paths that gate on
    it) must fail loudly on a `--base-ref` that does not exist, rather than
    let `list_base`'s empty result read as the legitimate "no base contract"
    (`BaseContractTests` above) -- a nonexistent ref is a broken invocation
    (a typo, or a commit this checkout never fetched), not an empty base.
    """

    def test_check_exits_2_on_a_nonexistent_base_ref(self):
        # This exact ref will never exist in real git history; HEAD (used
        # implicitly by every other test here reading the real repo) always
        # does, so this is not "git itself is unavailable".
        bogus = "definitely-not-a-real-ref-9c8f1a2"
        self.assertFalse(base_ref_exists(bogus))

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status = main(["check", "--base-ref", bogus])
        self.assertEqual(status, 2)
        self.assertIn(bogus, stderr.getvalue())
        self.assertIn("does not exist", stderr.getvalue())


class RequiredBumpTests(unittest.TestCase):
    def test_required_bump_major_for_breaking(self):
        changes = Changes(breaking=["removed x"], additive=[], descriptive=[])
        self.assertEqual(required_bump(changes), "major")

    def test_required_bump_minor_for_additive(self):
        changes = Changes(breaking=[], additive=["added x"], descriptive=[])
        self.assertEqual(required_bump(changes), "minor")

    def test_required_bump_none_for_descriptive_only(self):
        changes = Changes(breaking=[], additive=[], descriptive=["changed x"])
        self.assertEqual(required_bump(changes), "none")


class CheckTests(unittest.TestCase):
    def test_check_breaking_without_major_bump_is_error(self):
        changes = Changes(breaking=["removed operation x"], additive=[], descriptive=[])
        changelog = "# API changelog\n\n## 1.1.0 — breaking change\n"
        errors = check("1.0.0", "1.1.0", changes, changelog)
        self.assertTrue(any("MAJOR" in e for e in errors), errors)

    def test_check_additive_without_minor_bump_is_error(self):
        changes = Changes(breaking=[], additive=["added x"], descriptive=[])
        changelog = "# API changelog\n\n## 1.0.1 — additive change\n"
        errors = check("1.0.0", "1.0.1", changes, changelog)
        self.assertTrue(any("MINOR" in e for e in errors), errors)

    def test_check_descriptive_with_no_bump_passes(self):
        changes = Changes(breaking=[], additive=[], descriptive=["changed description"])
        errors = check("1.0.0", "1.0.0", changes, "# API changelog\n")
        self.assertEqual(errors, [])

    def test_check_version_change_without_changelog_section_is_error(self):
        changes = Changes(breaking=[], additive=[], descriptive=[])
        changelog = "# API changelog\n\n## 1.0.0 — initial contract\n"
        errors = check("1.0.0", "1.1.0", changes, changelog)
        self.assertTrue(any("CHANGELOG" in e for e in errors), errors)

    def test_check_passes_when_base_has_no_contract(self):
        changes = Changes(breaking=["added res.partner"], additive=["added op"], descriptive=[])
        changelog = "# API changelog\n\n## 1.0.0 — initial contract\n"
        errors = check(None, "1.0.0", changes, changelog)
        self.assertEqual(errors, [])

    def test_check_reports_a_downgrade_as_an_error_not_a_patch(self):
        # 2.0.0 -> 1.9.0 must never read as a "patch" bump (a minor digit
        # dropping while the major digit also drops is still a downgrade).
        changes = Changes(breaking=[], additive=[], descriptive=[])
        changelog = "# API changelog\n\n## 1.9.0 — descriptive change\n"
        errors = check("2.0.0", "1.9.0", changes, changelog)
        self.assertTrue(
            any("lower than base version" in e and "2.0.0" in e and "1.9.0" in e for e in errors),
            errors,
        )


class ChangelogTests(unittest.TestCase):
    def test_changelog_is_idempotent(self):
        # The initial-contract section is a summary, not a per-item list
        # (fix round 2), so a real `summary` is passed here to exercise the
        # actual call shape `changelog` uses.
        changes = Changes(breaking=[], additive=["added op"], descriptive=[])
        summary = ContractSummary(documents=3, operations=42, schemas=7)
        once = render_changelog(None, "1.0.0", changes, first=True, summary=summary)
        twice = render_changelog(once, "1.0.0", changes, first=True, summary=summary)
        self.assertEqual(once, twice)
        self.assertEqual(once.count("## 1.0.0"), 1)

    def test_initial_contract_section_is_a_summary(self):
        # No base contract: every item in `changes.additive` is there only
        # because there was nothing to compare against, so the section is
        # the heading plus one summary line, not a bullet per addition.
        changes = Changes(
            breaking=[], additive=["added operation x", "added schema y"], descriptive=[]
        )
        summary = ContractSummary(documents=33, operations=7981, schemas=471)
        section = changelog_section("1.0.0", changes, first=True, summary=summary)

        self.assertIn("## 1.0.0 — initial contract", section)
        self.assertIn("33 documents, 7981 operations, 471 schemas", section)
        self.assertIn("RFC 9457", section)
        self.assertIn("/docs/api/errors", section)
        self.assertNotIn("### Additive", section)
        self.assertNotIn("added operation x", section)
        self.assertNotIn("added schema y", section)

        non_blank_lines = [line for line in section.splitlines() if line.strip()]
        self.assertEqual(len(non_blank_lines), 2)  # the heading, and the summary line.

    def test_render_changelog_prepends_new_section_above_existing(self):
        v1_changes = Changes(breaking=[], additive=[], descriptive=[])
        after_v1 = render_changelog(None, "1.0.0", v1_changes, first=True)

        v2_changes = Changes(breaking=[], additive=["added op"], descriptive=[])
        after_v2 = render_changelog(after_v1, "1.1.0", v2_changes, first=False)

        self.assertIn("## 1.0.0", after_v2)
        self.assertIn("## 1.1.0", after_v2)
        self.assertLess(after_v2.index("## 1.1.0"), after_v2.index("## 1.0.0"))
        self.assertTrue(after_v2.startswith("# API changelog"))
        self.assertEqual(after_v2.count("## 1.0.0"), 1)
        self.assertEqual(after_v2.count("## 1.1.0"), 1)


class FormatChangesReportTests(unittest.TestCase):
    """`format_changes_report` is the `check` CLI's printed report, factored
    out so the no-base-contract behavior is testable without stubbing the
    git layer (fix round 2)."""

    def test_check_without_base_prints_counts_not_lists(self):
        changes = Changes(
            breaking=[], additive=["added operation a", "added operation b", "added operation c"], descriptive=[]
        )
        report = format_changes_report(changes, base_version=None)

        self.assertEqual(report, "breaking: 0, additive: 3, descriptive: 0")
        self.assertNotIn("added operation", report)

    def test_check_with_base_prints_full_lists(self):
        changes = Changes(breaking=["removed operation x"], additive=[], descriptive=[])
        report = format_changes_report(changes, base_version="1.0.0")

        self.assertIn("Breaking:", report)
        self.assertIn("removed operation x", report)
        self.assertNotIn("breaking: 1", report)


if __name__ == "__main__":
    unittest.main()
