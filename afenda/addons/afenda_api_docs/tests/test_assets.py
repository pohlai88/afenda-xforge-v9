import json
import re
import tempfile
from pathlib import Path

from odoo.tests import TransactionCase, tagged

from odoo.addons.afenda_api_docs.assets import (
    _app_closures,
    asset_areas,
    render_asset,
    write_assets,
)
from odoo.addons.afenda_api_docs.asset_rules import (
    RESERVED_AREAS,
    assign_area,
    manifest_applications,
)
from odoo.addons.afenda_api_docs.openapi import build_document

# afenda/addons/afenda_api_docs/openapi (the committed asset,
# AFD-ARCH-CORR-0005) and, four parents up from this file, the repo's own
# `addons/` (afenda/addons/afenda_api_docs/tests -> afenda_api_docs -> addons
# -> afenda -> repo root), which is what `manifest_applications` must be
# checked against - never `afenda/addons`, which holds AFENDA's own modules,
# none of which are `application: True`.
_OPENAPI_DIR = Path(__file__).resolve().parents[1] / "openapi"
_REPO_ADDONS_ROOT = Path(__file__).resolve().parents[4] / "addons"

# Every `description`, `summary`, `title` and `x-enum-labels` value is prose
# (AFD-ARCH-CORR-0004's aliasing split, aliasing.py); everything else in a
# committed document - keys, `operationId`, enum values, `$ref` - is a wire
# value and is not walked. A superset of test_identity.py's own PROSE_KEYS
# (which omits `summary`, since on the *live* document `summary` is always
# the method name, a wire value): the committed asset's own task brief
# named `summary` explicitly too, so both are checked here.
_COMMITTED_PROSE_KEYS = ("description", "summary", "title", "x-enum-labels")


def _write_manifest(root, name, application=True, installable=None):
    module_dir = Path(root) / name
    module_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"name": name, "application": application}
    if installable is not None:
        manifest["installable"] = installable
    (module_dir / "__manifest__.py").write_text(repr(manifest), encoding="utf-8")


@tagged("post_install", "-at_install")
class TestAssignArea(TransactionCase):
    """Five hand-built-closure cases (AFD-ARCH-CORR-0007, rules 2, 4, 5)."""

    def test_the_apps_own_module_goes_to_that_app(self):
        closures = {
            "sale": frozenset({"sale", "base"}),
            "purchase": frozenset({"purchase", "base"}),
        }
        self.assertEqual(assign_area("sale", closures), "sale")

    def test_a_module_in_every_closure_goes_to_core(self):
        closures = {
            "sale": frozenset({"sale", "base"}),
            "purchase": frozenset({"purchase", "base"}),
        }
        # "base" is in both closures and is not itself an app key.
        self.assertEqual(assign_area("base", closures), "core")

    def test_a_module_in_no_closure_goes_to_core(self):
        closures = {
            "sale": frozenset({"sale", "base"}),
            "purchase": frozenset({"purchase", "base"}),
        }
        self.assertEqual(assign_area("nowhere_module", closures), "core")

    def test_of_two_candidates_the_smaller_closure_wins(self):
        closures = {
            "sale": frozenset({"sale", "base", "stock"}),
            "mrp": frozenset({"mrp", "base", "stock", "sale"}),
            # A third app that does NOT depend on "stock", so "stock" is a
            # candidate of two (not all) apps - otherwise rule 4 ("in every
            # closure") would fire instead of rule 5.
            "website": frozenset({"website", "base"}),
        }
        # "stock" is in sale's and mrp's closures; sale's (3) is smaller than mrp's (4).
        self.assertEqual(assign_area("stock", closures), "sale")

    def test_an_equal_tie_goes_to_the_alphabetical_first(self):
        closures = {
            "zeta": frozenset({"zeta", "base", "shared"}),
            "alpha": frozenset({"alpha", "base", "shared"}),
            # A third app that does NOT depend on "shared", for the same
            # reason as above.
            "website": frozenset({"website", "base"}),
        }
        # Both candidate closures contain "shared" and are the same size (3).
        self.assertEqual(assign_area("shared", closures), "alpha")


@tagged("post_install", "-at_install")
class TestManifestApplications(TransactionCase):
    def test_manifest_applications_reads_only_installable_applications(self):
        with tempfile.TemporaryDirectory() as root:
            _write_manifest(root, "an_app")  # application: True, installable default
            _write_manifest(root, "an_uninstallable_app", installable=False)
            _write_manifest(root, "not_an_app", application=False)
            self.assertEqual(manifest_applications(Path(root)), ["an_app"])


@tagged("post_install", "-at_install")
class TestAssetAreas(TransactionCase):
    def test_ir_models_are_technical(self):
        areas = asset_areas(self.env)
        ir_models = [
            name for name in self.env.registry.models
            if (name == "ir" or name.startswith("ir."))
            and not self.env[name]._abstract
            and not self.env[name]._transient
        ]
        self.assertTrue(ir_models)
        self.assertIn("technical", areas)
        for name in ir_models:
            self.assertIn(name, areas["technical"])

    def test_areas_cover_every_concrete_model_once(self):
        areas = asset_areas(self.env)
        expected = sorted(
            name for name, model_cls in self.env.registry.models.items()
            if not model_cls._abstract and not model_cls._transient
        )
        got_flat = [name for names in areas.values() for name in names]
        self.assertEqual(sorted(got_flat), expected)
        # No duplicates: the flat count matches the deduplicated count.
        self.assertEqual(len(got_flat), len(expected))


@tagged("post_install", "-at_install")
class TestAssetDynamicEnum(TransactionCase):
    def test_asset_omits_dynamic_enums(self):
        # res.partner.lang: selection is a bound method
        # (odoo/addons/base/models/res_partner.py, `_lang_get`) - dynamic
        # under the general callable/method-name rule.
        lang_field = self.env["res.partner"]._fields["lang"]
        self.assertTrue(callable(lang_field.selection) or isinstance(lang_field.selection, str))

        # res.partner.tz is a *static* list at the field-object level
        # (odoo/addons/base/models/res_partner.py:40,223 -
        # `fields.Selection(_tzs, ...)` passes the module-level list built
        # from pytz at import time, never the `_tz_get` method) - the
        # general rule alone would miss it. It is dynamic only via the
        # named ENVIRONMENT_DERIVED_SELECTIONS exception (amended
        # AFD-ARCH-CORR-0011, commit e344ed3c8).
        tz_field = self.env["res.partner"]._fields["tz"]
        self.assertFalse(callable(tz_field.selection) or isinstance(tz_field.selection, str))

        # res.users.tz is auto-created by `_inherits` delegation
        # (odoo/orm/model_classes.py:500-504) as related="partner_id.tz",
        # resolving through `related_field` to that very same
        # res.partner.tz field object - so it must be caught too.
        users_tz_field = self.env["res.users"]._fields["tz"]
        self.assertEqual(users_tz_field.related, "partner_id.tz")

        live = build_document(self.env, names=["res.partner", "res.users"], asset=False)
        asset = build_document(self.env, names=["res.partner", "res.users"], asset=True)

        for model_name in ("res.partner", "res.users"):
            tz_asset = asset["components"]["schemas"][model_name]["properties"]["tz"]
            self.assertNotIn("enum", tz_asset, model_name)
            self.assertNotIn("x-enum-labels", tz_asset, model_name)
            self.assertTrue(tz_asset.get("x-afenda-dynamic-enum"), model_name)

            tz_live = live["components"]["schemas"][model_name]["properties"]["tz"]
            self.assertTrue(tz_live.get("enum"), model_name)

        lang_asset = asset["components"]["schemas"]["res.partner"]["properties"]["lang"]
        self.assertNotIn("enum", lang_asset)
        self.assertNotIn("x-enum-labels", lang_asset)
        self.assertTrue(lang_asset.get("x-afenda-dynamic-enum"))

        lang_live = live["components"]["schemas"]["res.partner"]["properties"]["lang"]
        self.assertTrue(lang_live.get("enum"))

        # A static selection keeps its enum in the asset document too.
        static_field = self.env["res.partner"]._fields["type"]
        self.assertFalse(callable(static_field.selection) or isinstance(static_field.selection, str))
        type_asset = asset["components"]["schemas"]["res.partner"]["properties"]["type"]
        self.assertTrue(type_asset.get("enum"))
        self.assertNotIn("x-afenda-dynamic-enum", type_asset)


@tagged("post_install", "-at_install")
class TestRenderAsset(TransactionCase):
    def test_render_has_no_build_or_time_markers(self):
        content = render_asset(self.env, "core", ["res.partner", "res.users"])
        self.assertNotIn(b"x-afenda-build", content)
        self.assertIsNone(re.search(rb"\d{4}-\d{2}-\d{2}T", content))

    def test_render_is_structurally_valid_openapi_31(self):
        content = render_asset(self.env, "core", ["res.partner", "res.users"])
        import json
        doc = json.loads(content)

        for key in ("openapi", "info", "paths", "components"):
            self.assertIn(key, doc)
        self.assertEqual(doc["openapi"], "3.1.0")
        self.assertTrue(doc["paths"])

        def walk(node):
            if isinstance(node, dict):
                ref = node.get("$ref")
                if ref:
                    prefix, kind, name = ref.rsplit("/", 2)
                    self.assertEqual(prefix, "#/components")
                    self.assertIn(name, doc["components"][kind])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(doc)

        for item in doc["paths"].values():
            post = item["post"]
            self.assertIn("operationId", post)
            self.assertIn("requestBody", post)
            self.assertIn("responses", post)


@tagged("post_install", "-at_install")
class TestWriteAssets(TransactionCase):
    def _installed_app_names(self):
        return sorted(
            self.env["ir.module.module"].sudo()
            .search([("state", "=", "installed"), ("application", "=", True)])
            .mapped("name")
        )

    def test_write_refuses_a_database_with_different_apps(self):
        with tempfile.TemporaryDirectory() as addons_root, \
             tempfile.TemporaryDirectory() as out_dir:
            for app in self._installed_app_names():
                _write_manifest(addons_root, app)
            # An application the fixture names but the database never installed.
            _write_manifest(addons_root, "zzz_not_installed_app")

            with self.assertRaises(ValueError) as capture:
                write_assets(self.env, Path(out_dir), Path(addons_root))
            self.assertIn("zzz_not_installed_app", str(capture.exception))
            self.assertEqual(list(Path(out_dir).iterdir()), [])

    def test_write_removes_stale_area_files_but_keeps_the_changelog(self):
        with tempfile.TemporaryDirectory() as addons_root, \
             tempfile.TemporaryDirectory() as out_dir:
            for app in self._installed_app_names():
                _write_manifest(addons_root, app)

            out_dir = Path(out_dir)
            stale = out_dir / "some_stale_area.json"
            stale.write_text("{}", encoding="utf-8")
            changelog = out_dir / "CHANGELOG.md"
            changelog.write_text("# Changelog\n", encoding="utf-8")

            expected_areas = asset_areas(self.env)
            count = write_assets(self.env, out_dir, Path(addons_root))

            self.assertEqual(count, len(expected_areas))
            self.assertFalse(stale.exists())
            self.assertEqual(changelog.read_text(encoding="utf-8"), "# Changelog\n")
            for area in expected_areas:
                self.assertTrue((out_dir / f"{area}.json").exists())


@tagged("post_install", "-at_install")
class TestCommittedAsset(TransactionCase):
    """Checks over the files actually committed under `openapi/*.json`.

    Reads only `openapi/*.json` - never `CHANGELOG.md`, which Task 5 adds -
    and needs no live registry matching the full 34-application set: both
    checks are static, over whatever is on disk right now.
    """

    def test_committed_asset_matches_the_supported_applications(self):
        files = sorted(_OPENAPI_DIR.glob("*.json"))
        self.assertTrue(files, "no committed OpenAPI documents; run the exporter first")
        allowed = set(manifest_applications(_REPO_ADDONS_ROOT)) | set(RESERVED_AREAS)
        stems = {path.stem for path in files}
        self.assertTrue(stems.issubset(allowed), stems - allowed)

    def test_committed_asset_covers_every_application_that_owns_a_model(self):
        # The subset check above (every committed stem is a supported
        # application or a reserved area) says nothing about the reverse:
        # that a non-empty area actually got a file. `core` and `technical`
        # are always non-empty on any database with at least one installed
        # module (technical: ir.* models; core: base itself, in every
        # closure). Rule 2 (asset_rules.py's `assign_area`) puts a module's
        # *own* models in that module's own area regardless of which other
        # applications happen to be installed alongside it, so this check
        # is independent of whether this test runs against `afenda_t2`'s
        # small install or the full 34-application `afenda_assets` used to
        # generate these files - whatever this database's own installed
        # applications are, each one that owns a concrete model must have a
        # file here too.
        stems = {path.stem for path in _OPENAPI_DIR.glob("*.json")}
        self.assertIn("core", stems)
        self.assertIn("technical", stems)

        apps = self.env["ir.module.module"].sudo().search(
            [("state", "=", "installed"), ("application", "=", True)]
        )
        for app in apps:
            owns_a_model = any(
                not self.env[name]._abstract
                and not self.env[name]._transient
                and self.env[name]._original_module == app.name
                for name in self.env.registry.models
            )
            if owns_a_model:
                self.assertIn(app.name, stems, app.name)

    def test_committed_asset_carries_no_odoo_identity_in_prose(self):
        # Local import: test_identity.py defines an HttpCase subclass, which
        # this TransactionCase-only test does not need to load merely to
        # reuse the tell list and the shared walker.
        from .test_identity import ODOO_TELLS, walk_prose  # noqa: PLC0415

        files = sorted(_OPENAPI_DIR.glob("*.json"))
        self.assertTrue(files, "no committed OpenAPI documents; run the exporter first")

        for path in files:
            doc = json.loads(path.read_text(encoding="utf-8"))
            prose = walk_prose(doc, keys=_COMMITTED_PROSE_KEYS)
            self.assertTrue(prose, path.name)
            for text in prose:
                if isinstance(text, str):
                    for tell in ODOO_TELLS:
                        self.assertNotIn(tell, text, f"{tell!r} in {path.name}")


@tagged("post_install", "-at_install")
class TestReservedAreaGuard(TransactionCase):
    def test_an_installed_application_named_core_is_refused(self):
        # RESERVED_AREAS = ("core", "technical"): an installed application
        # literally named "core" would be indistinguishable from the area
        # every closure-spanning module lands in (assets.py's
        # `_app_closures`), so it must be refused rather than silently
        # shadowed.
        self.env["ir.module.module"].create({
            "name": "core",
            "state": "installed",
            "application": True,
        })
        self.assertIn("core", RESERVED_AREAS)
        with self.assertRaises(ValueError) as capture:
            _app_closures(self.env)
        self.assertIn("core", str(capture.exception))
