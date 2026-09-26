# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""Pure rules for grouping OpenAPI models into asset areas (AFD-ARCH-CORR-0007).

No ``odoo`` import: a CI job that never boots a database still needs to
check `manifest_applications` against the committed asset areas (see
`afenda/tools/export_openapi_shell.py` and the CI workflow that calls
``manifest_applications`` directly, importing this module on a bare
interpreter with ``afenda/addons/afenda_api_docs`` on ``sys.path``).
"""
import ast
from pathlib import Path

# `assets.py` reserves these two area names: "core" is where a module in
# every installed application's dependency closure (or in none) lands, and
# "technical" is where every `ir.*` model lands. Neither is ever the name of
# an installed application module - `assign_area` would otherwise be unable
# to tell "the core area" from "the app literally named core".
RESERVED_AREAS = ("core", "technical")


def manifest_applications(addons_root: Path) -> list[str]:
    """Sorted names of the installable application modules under `addons_root`.

    Reads each `<addons_root>/<module>/__manifest__.py` with
    `ast.literal_eval` - never `import`s it, so this runs on a bare
    interpreter with no `odoo` on the path. A module is an application when
    its manifest sets `application: True` and does not set
    `installable: False` (the default is installable).
    """
    addons_root = Path(addons_root)
    apps = []
    for manifest_path in sorted(addons_root.glob("*/__manifest__.py")):
        manifest = ast.literal_eval(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("application") and manifest.get("installable", True) is not False:
            apps.append(manifest_path.parent.name)
    return sorted(apps)


def assign_area(module: str, app_closures: dict[str, frozenset[str]]) -> str:
    """The asset area for a module that is not itself `ir.*`-named (rule 3, on the caller).

    Implements rules 2, 4 and 5 of AFD-ARCH-CORR-0007, in that order:

    2. `module` is itself an installed application (a key of `app_closures`):
       its own area.
    4. `module` is in the dependency closure of every installed application,
       or of none of them: `"core"`.
    5. Otherwise: the application with the smallest closure containing
       `module`; an equal tie goes to the alphabetically first application
       name.

    `app_closures` maps each installed application's name to its full
    dependency closure (itself included), as `assets.py` computes it from
    `ir.module.module.dependencies_id.name` over installed modules.
    """
    if module in app_closures:
        return module

    containing = [app for app, closure in app_closures.items() if module in closure]
    if not containing or len(containing) == len(app_closures):
        return "core"

    containing.sort(key=lambda app: (len(app_closures[app]), app))
    return containing[0]
