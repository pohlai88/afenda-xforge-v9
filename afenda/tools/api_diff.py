"""The OpenAPI change checker and version gate for the AFENDA-owned API contract.

Reads the committed OpenAPI 3.1 documents at `ASSET_DIR/<area>.json` (produced
by `afenda/addons/afenda_api_docs/openapi.py`) at a base git ref and at HEAD
(the working tree), computes the change classes from gc-change-gate.md, and
gates the required version bump against `api_version.py` and `CHANGELOG.md`.

Standard library only.
"""
from __future__ import annotations

import argparse
import ast
import copy
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

ASSET_DIR = "afenda/addons/afenda_api_docs/openapi"
VERSION_FILE = "afenda/addons/afenda_api_docs/api_version.py"

_CHANGELOG_NAME = "CHANGELOG.md"
_REQUEST_BODY_REF_PREFIX = "#/components/requestBodies/"

_BUMP_RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}
_BUMP_LABEL = {
    "major": "breaking change",
    "minor": "additive change",
    "none": "descriptive change",
}


@dataclass
class Changes:
    """The three change classes from gc-change-gate.md, each a sorted list of messages."""

    breaking: list = field(default_factory=list)
    additive: list = field(default_factory=list)
    descriptive: list = field(default_factory=list)


@dataclass
class ContractSummary:
    """The counts `changelog_section` needs for the initial-contract summary line."""

    documents: int
    operations: int
    schemas: int


# --------------------------------------------------------------------------
# Reading documents: base (a git ref) and head (the working tree).
# --------------------------------------------------------------------------

def base_ref_exists(ref: str) -> bool:
    """Whether `ref` resolves to a commit at all.

    `git ls-tree` on a nonexistent ref also exits non-zero, the same as it
    does when the ref exists but ASSET_DIR is simply absent there — so
    `list_base` cannot tell "no base contract" (a real ref, predating the
    asset) apart from "no such ref" (a broken invocation: a typo, a
    `--base-ref` naming a commit the checkout never fetched) by its return
    value alone. Callers must check this first and fail loudly on a missing
    ref, rather than let it read as an innocuous empty base contract.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def list_base(ref: str) -> list:
    """The committed `*.json` documents under ASSET_DIR at `ref`.

    An empty list means no base contract: ASSET_DIR is absent at `ref` — a
    real, existing ref that predates the asset (or never carried it). `ref`
    itself must already be known to exist (`base_ref_exists`); this function
    does not distinguish a missing ref from a missing ASSET_DIR (`git
    ls-tree` reports nothing for either), so a caller that skips that check
    would silently read a bad `--base-ref` as "no base contract" instead of
    an error.
    """
    result = subprocess.run(
        ["git", "ls-tree", "--name-only", ref, f"{ASSET_DIR}/"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return sorted(line for line in result.stdout.splitlines() if line.endswith(".json"))


def list_head() -> list:
    """The `*.json` documents under ASSET_DIR in the working tree."""
    root = Path(ASSET_DIR)
    if not root.exists():
        return []
    return sorted(str(path) for path in root.glob("*.json"))


def get_text_at_ref(ref: str, path: str):
    """`git show <ref>:<path>`, or None when that path is absent at `ref`."""
    result = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout


def read_local_text(path: str):
    """The working-tree file at `path`, or None when it does not exist."""
    file_path = Path(path)
    return file_path.read_text(encoding="utf-8") if file_path.exists() else None


def read_version(text: str) -> str:
    """`API_VERSION = "..."` from `api_version.py` source, via `ast` (never imported)."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "API_VERSION":
                    return ast.literal_eval(node.value)
    raise ValueError("API_VERSION assignment not found")


def base_contract(names: list, version_text):
    """The one "no base contract" rule (gc-change-gate.md), shared by `check`
    and `changelog`.

    "No base contract" means either ASSET_DIR or `api_version.py` is absent
    at the base — so a base with documents (`names` non-empty) but no
    `api_version.py` (`version_text` is None) is still no base contract, and
    so is the reverse. Only when both are present is there a real
    `base_version` to gate against. Returns `(names, base_version | None)`.
    """
    if not names or version_text is None:
        return names, None
    return names, read_version(version_text)


# --------------------------------------------------------------------------
# Building the union of all documents, request bodies resolved per-document.
# --------------------------------------------------------------------------

def _resolve_item(item: dict, request_bodies: dict) -> dict:
    """A path item with its `post.requestBody` `$ref` resolved, if any."""
    item = copy.deepcopy(item)
    post = item.get("post")
    if isinstance(post, dict):
        request_body = post.get("requestBody")
        if isinstance(request_body, dict) and "$ref" in request_body:
            ref = request_body["$ref"]
            if ref.startswith(_REQUEST_BODY_REF_PREFIX):
                name = ref[len(_REQUEST_BODY_REF_PREFIX):]
                post["requestBody"] = copy.deepcopy(request_bodies.get(name, {}))
    return item


def load_set(get_text: Callable[[str], "str | None"], names: list) -> dict:
    """The union of `paths` and `components.schemas` over every named document.

    Each document's `requestBody` `$ref`s are resolved against its own
    `components.requestBodies` before the union, so shared bodies from
    different documents never collide. `info` is ignored entirely. A model
    (or path) defined identically in two documents merges without conflict;
    a model moving from one area file to another is therefore no change, as
    long as its content is unchanged.
    """
    paths: dict = {}
    schemas: dict = {}
    for name in names:
        text = get_text(name)
        if text is None:
            continue
        doc = json.loads(text)
        components = doc.get("components", {})
        request_bodies = components.get("requestBodies", {})
        for path, item in doc.get("paths", {}).items():
            paths[path] = _resolve_item(item, request_bodies)
        schemas.update(components.get("schemas", {}))
    return {"paths": paths, "schemas": schemas}


# --------------------------------------------------------------------------
# The diff itself.
# --------------------------------------------------------------------------

def _enum_or_none(prop: dict):
    """The property's enum values, or None when it has none (or a dynamic one)."""
    if prop.get("x-afenda-dynamic-enum"):
        return None
    return prop.get("enum")


def _diff_property(base_prop: dict, head_prop: dict, label: str, changes: Changes) -> None:
    base_type = base_prop.get("type")
    head_type = head_prop.get("type")
    if base_type != head_type:
        changes.breaking.append(f"{label} changed type from {base_type!r} to {head_type!r}")

    base_enum = _enum_or_none(base_prop)
    head_enum = _enum_or_none(head_prop)
    if base_enum is not None and head_enum is not None:
        for value in set(base_enum) - set(head_enum):
            changes.breaking.append(f"{label} removed enum value {value!r}")
        for value in set(head_enum) - set(base_enum):
            changes.additive.append(f"{label} added enum value {value!r}")

    for key in ("title", "description"):
        if base_prop.get(key) != head_prop.get(key):
            changes.descriptive.append(f"{label} changed {key}")


def _diff_object_schema(base_schema, head_schema, label: str, changes: Changes) -> None:
    base_schema = base_schema or {}
    head_schema = head_schema or {}

    for key in ("title", "description"):
        if base_schema.get(key) != head_schema.get(key):
            changes.descriptive.append(f"{label} changed {key}")

    base_props = base_schema.get("properties") or {}
    head_props = head_schema.get("properties") or {}
    base_required = set(base_schema.get("required") or [])
    head_required = set(head_schema.get("required") or [])

    for name in set(base_props) - set(head_props):
        changes.breaking.append(f"removed property {label}.{name}")
    for name in set(head_props) - set(base_props):
        changes.additive.append(f"added property {label}.{name}")
    for name in set(base_props) & set(head_props):
        _diff_property(base_props[name], head_props[name], f"{label}.{name}", changes)

    for name in head_required - base_required:
        changes.breaking.append(f"{label}.{name} is newly required")
    for name in base_required - head_required:
        changes.additive.append(f"{label}.{name} is no longer required")


def _request_schema(post: dict):
    request_body = post.get("requestBody") or {}
    return request_body.get("content", {}).get("application/json", {}).get("schema")


def _diff_operation(base_post: dict, head_post: dict, path: str, changes: Changes) -> None:
    _diff_object_schema(_request_schema(base_post), _request_schema(head_post), f"{path} requestBody", changes)
    if base_post.get("description") != head_post.get("description"):
        changes.descriptive.append(f"{path} changed description")


def diff(base: dict, head: dict) -> Changes:
    """The change classes between two `load_set` results (gc-change-gate.md)."""
    changes = Changes()

    base_paths = base.get("paths", {})
    head_paths = head.get("paths", {})
    for path in set(base_paths) - set(head_paths):
        changes.breaking.append(f"removed operation {path}")
    for path in set(head_paths) - set(base_paths):
        changes.additive.append(f"added operation {path}")
    for path in set(base_paths) & set(head_paths):
        _diff_operation(base_paths[path].get("post", {}), head_paths[path].get("post", {}), path, changes)

    base_schemas = base.get("schemas", {})
    head_schemas = head.get("schemas", {})
    for name in set(base_schemas) - set(head_schemas):
        changes.breaking.append(f"removed schema {name}")
    for name in set(head_schemas) - set(base_schemas):
        changes.additive.append(f"added schema {name}")
    for name in set(base_schemas) & set(head_schemas):
        _diff_object_schema(base_schemas[name], head_schemas[name], f"schema {name}", changes)

    changes.breaking = sorted(set(changes.breaking))
    changes.additive = sorted(set(changes.additive))
    changes.descriptive = sorted(set(changes.descriptive))
    return changes


def required_bump(changes: Changes) -> "Literal['major', 'minor', 'none']":
    if changes.breaking:
        return "major"
    if changes.additive:
        return "minor"
    return "none"


# --------------------------------------------------------------------------
# The version gate.
# --------------------------------------------------------------------------

def _version_bump(base_version: str, head_version: str) -> str:
    """The bump class from `base_version` to `head_version`.

    `"downgrade"` when `head_version` is lower than `base_version` (tuple
    comparison over the three integer parts: a lower major always sorts
    below regardless of minor/patch, matching semantic-version ordering) -
    `check` reports that as an error in its own right, never as a silent
    `"patch"`.
    """
    base_parts = tuple(int(part) for part in base_version.split("."))
    head_parts = tuple(int(part) for part in head_version.split("."))
    if head_parts == base_parts:
        return "none"
    if head_parts < base_parts:
        return "downgrade"
    if head_parts[0] > base_parts[0]:
        return "major"
    if head_parts[0] == base_parts[0] and head_parts[1:2] > base_parts[1:2]:
        return "minor"
    return "patch"


def check(base_version, head_version: str, changes: Changes, changelog: str) -> list:
    """The gate errors: a downgrade, an insufficient version bump, or a
    missing changelog section.

    When `base_version` is None (no base contract), the bump check does not
    apply: the check passes as long as `changelog` has a section for
    `head_version` (gc-change-gate.md, "No base contract").
    """
    errors = []
    required = required_bump(changes)

    if base_version is not None:
        bump = _version_bump(base_version, head_version)
        if bump == "downgrade":
            errors.append(
                f"head version {head_version} is lower than base version {base_version}"
            )
        else:
            bump_rank = _BUMP_RANK[bump]
            if required == "major" and bump_rank < _BUMP_RANK["major"]:
                errors.append("breaking changes require a MAJOR version bump")
            elif required == "minor" and bump_rank < _BUMP_RANK["minor"]:
                errors.append("additive changes require at least a MINOR version bump")

    if base_version != head_version:
        heading = re.compile(rf"^## {re.escape(head_version)}\b", re.MULTILINE)
        if not heading.search(changelog or ""):
            errors.append(f"CHANGELOG.md is missing a section for {head_version}")

    return errors


# --------------------------------------------------------------------------
# CHANGELOG.md.
# --------------------------------------------------------------------------

def changelog_section(
    version: str, changes: Changes, first: bool, summary: "ContractSummary | None" = None
) -> str:
    """The Markdown section for one version, headed `## <version> — <suffix>`.

    `first` (no base contract) writes the heading plus one summary line,
    not a per-item list: against an empty base, every operation and schema
    in `head` is additive by construction, so a full listing would repeat
    one bullet per item in the initial surface (thousands, for a real API)
    both in the committed file and in anything that captures `check`'s or
    this command's output (a CI step summary, for one). `summary` supplies
    the counts for that line; a missing `summary` reads as all-zero rather
    than raising, since a heading is still owed even without one.

    A version-to-version diff (`first` is False, a base contract exists)
    keeps the full Breaking/Additive/Descriptive lists, unchanged.
    """
    if first:
        counts = summary or ContractSummary(documents=0, operations=0, schemas=0)
        heading = f"## {version} — initial contract"
        line = (
            f"Initial published contract: {counts.documents} documents, "
            f"{counts.operations} operations, {counts.schemas} schemas. "
            "Errors are RFC 9457 Problem Details (see /docs/api/errors)."
        )
        return f"{heading}\n\n{line}\n"

    heading = f"## {version} — {_BUMP_LABEL[required_bump(changes)]}"
    lines = [heading, ""]
    for title, items in (
        ("Breaking", changes.breaking),
        ("Additive", changes.additive),
        ("Descriptive", changes.descriptive),
    ):
        if not items:
            continue
        lines.append(f"### {title}")
        lines.extend(f"- {item}" for item in items)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def render_changelog(
    existing, version: str, changes: Changes, first: bool, summary: "ContractSummary | None" = None
) -> str:
    """`existing` with the section for `version` prepended; idempotent.

    A section already present (matched by heading prefix, since headings
    carry a suffix) means no change. A missing or empty `existing` starts a
    fresh file under a top `# API changelog` title.
    """
    heading = re.compile(rf"^## {re.escape(version)}\b", re.MULTILINE)
    if existing and heading.search(existing):
        return existing

    section = changelog_section(version, changes, first, summary)
    if not existing or not existing.strip():
        return "# API changelog\n\n" + section

    lines = existing.splitlines(keepends=True)
    insert_at = 1 if lines and lines[0].startswith("# ") else 0
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    return "".join(lines[:insert_at]) + "\n" + section + "".join(lines[insert_at:])


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------

def _load_head() -> dict:
    return load_set(read_local_text, list_head())


def _base_contract_at(base_ref: str):
    """`base_contract`, fed from the actual base ref (git ls-tree + git show)."""
    names = list_base(base_ref)
    version_text = get_text_at_ref(base_ref, VERSION_FILE)
    return base_contract(names, version_text)


def _head_version():
    text = read_local_text(VERSION_FILE)
    if text is None:
        return None
    return read_version(text)


def format_changes_report(changes: Changes, base_version) -> str:
    """The `check` CLI's printed change report.

    With a base contract (`base_version` is not None), the full
    Breaking/Additive/Descriptive lists, as before. Without one, every item
    in `head` is additive by construction (there is nothing to compare
    against), so a full listing is thousands of lines for a real API and
    would flood a CI step summary that captures it; the three list counts
    are printed instead (`base_version` doubles as the base-contract flag,
    since `_base_contract_at`/`base_contract` are the one place that
    decides it).
    """
    if base_version is None:
        return (
            f"breaking: {len(changes.breaking)}, "
            f"additive: {len(changes.additive)}, "
            f"descriptive: {len(changes.descriptive)}"
        )
    lines = []
    for title, items in (
        ("Breaking", changes.breaking),
        ("Additive", changes.additive),
        ("Descriptive", changes.descriptive),
    ):
        lines.append(f"{title}:")
        lines.extend(f"  {item}" for item in items)
    return "\n".join(lines)


def _changelog_path() -> Path:
    return Path(ASSET_DIR) / _CHANGELOG_NAME


def _cmd_check(args: argparse.Namespace) -> int:
    if not base_ref_exists(args.base_ref):
        print(f"error: base ref {args.base_ref!r} does not exist", file=sys.stderr)
        return 2
    base_names, base_version = _base_contract_at(args.base_ref)
    base = load_set(lambda name: get_text_at_ref(args.base_ref, name), base_names)
    head = _load_head()
    changes = diff(base, head)
    print(format_changes_report(changes, base_version))

    if base_version is None:
        print("no base contract")

    head_version = _head_version()
    if head_version is None:
        print(f"error: {VERSION_FILE} not found", file=sys.stderr)
        return 1

    changelog_path = _changelog_path()
    changelog_text = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else ""

    errors = check(base_version, head_version, changes, changelog_text)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    return 1 if errors else 0


def _cmd_changelog(args: argparse.Namespace) -> int:
    if not base_ref_exists(args.base_ref):
        print(f"error: base ref {args.base_ref!r} does not exist", file=sys.stderr)
        return 2
    base_names, base_version = _base_contract_at(args.base_ref)
    base = load_set(lambda name: get_text_at_ref(args.base_ref, name), base_names)
    head_names = list_head()
    head = load_set(read_local_text, head_names)
    changes = diff(base, head)

    head_version = _head_version()
    if head_version is None:
        print(f"error: {VERSION_FILE} not found", file=sys.stderr)
        return 1

    changelog_path = _changelog_path()
    existing = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else None
    first = base_version is None
    summary = (
        ContractSummary(documents=len(head_names), operations=len(head["paths"]), schemas=len(head["schemas"]))
        if first
        else None
    )
    updated = render_changelog(existing, head_version, changes, first=first, summary=summary)
    if updated != existing:
        changelog_path.parent.mkdir(parents=True, exist_ok=True)
        changelog_path.write_text(updated, encoding="utf-8")
        print(f"wrote {changelog_path} for {head_version}")
    else:
        print(f"{changelog_path} already has a section for {head_version}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m afenda.tools.api_diff")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Gate the OpenAPI contract change.")
    check_parser.add_argument("--base-ref", required=True)
    check_parser.set_defaults(func=_cmd_check)

    changelog_parser = subparsers.add_parser("changelog", help="Write the CHANGELOG.md section for API_VERSION.")
    changelog_parser.add_argument("--base-ref", required=True)
    changelog_parser.set_defaults(func=_cmd_changelog)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
