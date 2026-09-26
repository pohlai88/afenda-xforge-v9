# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""Group the live registry into OpenAPI asset areas and write them to disk.

The committed assets live at `afenda/addons/afenda_api_docs/openapi/<area>.json`
(AFD-ARCH-CORR-0005); this module computes the `<area>` grouping and renders
each area's document. `asset_rules.py` holds the pure, odoo-free parts of the
area rule; this module supplies the odoo-dependent parts (the registry, the
installed module graph) and does the file I/O.
"""
import json
from pathlib import Path

from .asset_rules import RESERVED_AREAS, assign_area, manifest_applications
from .openapi import build_document


def _dependency_closure(module, direct_deps):
    """Every module `module` depends on, directly or indirectly, itself included."""
    seen = set()
    stack = [module]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(direct_deps.get(current, ()))
    return frozenset(seen)


def _app_closures(env):
    """{installed application name: its full dependency closure}.

    `dependencies_id.name` (odoo/addons/base/models/ir_module.py) gives each
    installed module's *direct* dependencies by name; the closure walks that
    graph. Only installed modules are considered - the running registry is
    the only one this document can describe.
    """
    installed = env["ir.module.module"].sudo().search([("state", "=", "installed")])
    direct_deps = {module.name: set(module.dependencies_id.mapped("name")) for module in installed}
    apps = sorted(module.name for module in installed if module.application)
    for app in apps:
        if app in RESERVED_AREAS:
            raise ValueError(
                f"installed application {app!r} collides with a reserved asset area name"
            )
    return {app: _dependency_closure(app, direct_deps) for app in apps}


def asset_areas(env):
    """{area: sorted [concrete model names]}, covering every concrete model once.

    Applies rule 1 (abstract and transient models are excluded) and rule 3
    (an `ir.*`-named model goes to `"technical"`) directly; every other
    model's module (`_original_module`) is resolved through `assign_area`
    (rules 2, 4, 5). An area with no models is simply absent, never an empty
    list - `write_assets` skips it, matching AFD-ARCH-CORR-0007's "an area
    with no models gets no file".
    """
    app_closures = _app_closures(env)
    areas = {}
    for model_name in env.registry.models:
        model = env[model_name]
        if model._abstract or model._transient:
            continue
        if model_name == "ir" or model_name.startswith("ir."):
            area = "technical"
        else:
            area = assign_area(model._original_module, app_closures)
        areas.setdefault(area, []).append(model_name)
    return {area: sorted(names) for area, names in areas.items() if names}


def render_asset(env, area, names):
    """The serialised bytes of one area's OpenAPI document (AFD-ARCH-CORR-0008).

    Built with `asset=True` (AFD-ARCH-CORR-0011: dynamic selections omit
    their `enum`). Serialisation is fixed by the asset contract: sorted
    keys, one-space indent, UTF-8, a trailing newline - so two builds of the
    same registry state are byte-identical and diff cleanly.
    """
    doc = build_document(env, names=names, asset=True)
    doc["info"]["x-afenda-area"] = area
    text = json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    return text.encode("utf-8")


def write_assets(env, out_dir, addons_root):
    """Write every non-empty area's document to `out_dir`; return how many.

    Refuses (`ValueError`, naming the missing and extra applications) before
    touching `out_dir` at all when the database's installed applications
    differ from `manifest_applications(addons_root)` - a document built
    against the wrong app set would silently mis-describe every other area
    too. On success, removes stale `*.json` files this run did not write
    (a renamed or removed area's old file must not linger) but never touches
    `CHANGELOG.md` or anything else under `out_dir`.
    """
    installed_apps = sorted(
        env["ir.module.module"].sudo()
        .search([("state", "=", "installed"), ("application", "=", True)])
        .mapped("name")
    )
    expected_apps = manifest_applications(addons_root)
    if installed_apps != expected_apps:
        missing = sorted(set(expected_apps) - set(installed_apps))
        extra = sorted(set(installed_apps) - set(expected_apps))
        raise ValueError(
            "installed applications differ from manifest_applications"
            f"({addons_root}): missing {missing}, extra {extra}"
        )

    areas = asset_areas(env)
    rendered = {area: render_asset(env, area, names) for area, names in areas.items()}

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for existing in out_dir.glob("*.json"):
        if existing.stem not in rendered:
            existing.unlink()
    for area, content in rendered.items():
        (out_dir / f"{area}.json").write_bytes(content)

    return len(rendered)
