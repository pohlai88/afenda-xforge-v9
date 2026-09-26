import re
from pathlib import Path

from werkzeug.urls import url_encode

from odoo import http
from odoo.http import request

from odoo.addons.afenda_runtime.problems import PROBLEM_CODES

from ..aliasing import alias_prose

# The Redoc bundle unconditionally renders an "API docs by Redocly" link with
# a logo fetched from cdn.redoc.ly (static/lib/redoc/README.md). Hiding the
# link with CSS would not stop an <img> from loading, and patching the
# vendored file would break its recorded hash, so the browser is told to
# refuse third-party images on this one page instead. Same per-response
# mechanism upstream uses on the login page (addons/web/controllers/home.py:153),
# including its `frame-ancestors 'self'` against framing by another origin.
_API_PAGE_CSP = "img-src 'self' data:; frame-ancestors 'self'"

# The committed OpenAPI asset areas (AFD-ARCH-CORR-0005), one file per
# non-empty area, written by `afenda/tools/export_openapi_shell.py` and
# committed to the repository - never generated at request time.
_OPENAPI_DIR = (Path(__file__).resolve().parents[1] / "openapi").resolve()
# The only shape `write_assets` ever names a file with (asset_rules.py:
# `manifest_applications` reads module directory names, which
# odoo/addons/base's own module-name column already restricts to this
# charset). Anything else - a dot, a slash, an encoded null byte, an
# uppercase letter, a trailing control character, or anything longer than
# any real module name - is refused before the filesystem is ever touched,
# so a path trick has nothing to work with even before the parent-directory
# check in `_resolve_committed_path` below.
#
# The length cap (64) is not merely cosmetic: `Path.is_file()` on a
# component longer than the filesystem's NAME_MAX raises `OSError`
# (`ENAMETOOLONG`), which an unhandled exception would turn into an
# authenticated 500 rather than the 404 every other rejected shape gets
# here - so the cap must reject before any filesystem call is made, not
# rely on catching that error after the fact (fix round 1, finding 4).
# Matched with `fullmatch`, never `match`: `match` alone lets `$` accept a
# string with one trailing newline (`re.match(r"^[a-z0-9_]+$", "core\n")`
# succeeds - `$` matches just before a trailing "\n" even without
# `re.MULTILINE`), which would let `area` carry one byte the regex was
# meant to refuse. `fullmatch` requires the whole string, "\n" included, to
# lie inside the character class, so it does not (fix round 1, finding 3).
_AREA_RE = re.compile(r"[a-z0-9_]{1,64}")


def _committed_areas():
    """Sorted stems of every committed OpenAPI asset area on disk."""
    return sorted(path.stem for path in _OPENAPI_DIR.glob("*.json"))


def _resolve_committed_path(area):
    """The `Path` of one committed area's file, or `None` if `area` is refused.

    Exposed as its own function (rather than inlined in the route) so its
    guard can be unit-tested directly, on shapes such as `".."`, `"../x"`,
    a trailing-newline area, and an over-length area, without going through
    HTTP or risking a request instead landing on some *other* route this
    controller does not own (see `tests/test_api_routes.py`'s
    `TestSpecRouteGuard`, and its docstring on why `/etc/passwd`-shaped
    vectors alone cannot exercise this function). Two independent checks,
    in this order: `_AREA_RE` first (a dot, a slash - encoded or not -, a
    control character, an uppercase letter, or too long a name never even
    reaches a path lookup), and only once that passes, that the resolved
    file's parent is still `_OPENAPI_DIR` (defence in depth against
    anything the regex alone might miss, e.g. a symlink) and that the file
    actually exists.
    """
    if not _AREA_RE.fullmatch(area):
        return None
    path = (_OPENAPI_DIR / f"{area}.json").resolve()
    if path.parent != _OPENAPI_DIR or not path.is_file():
        return None
    return path


class AfendaApiController(http.Controller):
    # auth='user' on /docs/openapi.json and /docs/api (not on
    # /docs/api/spec/<area>.json below, whose auth reasoning differs - see
    # its own comment): the live document lists every model and field the
    # caller can read, which is an information-disclosure surface, and is
    # generated per user - meaningless if it could be fetched anonymously.
    # werkzeug ranks these static rules above landing.py's
    # `/docs/<path:subpath>` catch-all.
    @http.route(
        "/docs/openapi.json",
        type="http", auth="user", methods=["GET"], website=False, sitemap=False,
    )
    def docs_openapi(self, app=None, **kwargs):
        # Built per user and cached server-side (models/api_docs.py); a shared
        # HTTP cache must never hold one user's document for another.
        return request.make_response(
            request.env["afenda.api.docs"]._openapi_json(app or None),
            headers=[
                ("Content-Type", "application/json; charset=utf-8"),
                ("Cache-Control", "private, no-store"),
            ],
        )

    @http.route(
        "/docs/api",
        type="http", auth="user", methods=["GET"], website=False, sitemap=False,
    )
    def docs_api(self, app=None, **kwargs):
        spec_url = "/docs/openapi.json"
        if app:
            spec_url += "?" + url_encode({"app": app})
        response = request.render("afenda_api_docs.api_reference", {
            "spec_url": spec_url,
            "app": app or "",
            "apps": self._app_choices(),
            "asset_areas": _committed_areas(),
        })
        response.headers["Content-Security-Policy"] = _API_PAGE_CSP
        return response

    # auth='user', but unlike /docs/openapi.json this is NOT gating a
    # per-caller information disclosure: every committed file is the exact
    # same bytes for every caller (built once, as base.user_admin, on a
    # fresh installation - AFD-ARCH-CORR-0006) and carries no data from
    # *this* server - it is the repository's own published contract, not a
    # view of this database. `auth="user"` stays anyway (controller
    # ruling, fix round 1 finding 8): a portal user can fetch it, and that
    # is fine, since there is nothing server-specific in it to disclose;
    # the gate is here only to keep this route's audience the same as the
    # rest of `/docs/api` and `/docs/openapi.json`, not because the bytes
    # themselves need protecting.
    @http.route(
        "/docs/api/spec/<string:area>.json",
        type="http", auth="user", methods=["GET"], website=False, sitemap=False,
    )
    def docs_api_spec(self, area, **kwargs):
        """Serve one committed OpenAPI asset area's bytes, verbatim, from disk."""
        path = _resolve_committed_path(area)
        if path is None:
            return request.not_found()
        return request.make_response(
            path.read_bytes(),
            headers=[
                ("Content-Type", "application/json"),
                ("Cache-Control", "private, no-store"),
            ],
        )

    # auth='public': the "type" field of every JSON-2 error body, signed in
    # or not, points here (afenda_runtime/problems.py, models/ir_http.py), so
    # this page must be reachable without a session too.
    @http.route(
        "/docs/api/errors",
        type="http", auth="public", methods=["GET"], website=False, sitemap=False,
    )
    def docs_api_errors(self, **kwargs):
        # no_footer: same reasoning as landing.py:103-107 - this route is
        # website=False, so request.is_frontend never turns True and
        # portal's footer-injected language selector 500s on the missing
        # frontend_languages value. The template is generated and never
        # sets this itself, so it is supplied here instead.
        return request.render("afenda_api_docs.api_errors", {
            "codes": PROBLEM_CODES,
            "no_footer": True,
        })

    def _app_choices(self):
        """(name, label) of each installed module that defines a concrete model.

        Offered only to users who may read ir.module.module (group_system,
        odoo/addons/base/security/ir.model.access.csv) - no sudo(): anyone
        else gets the default document and can still pass ?app= by hand.
        The name is a wire value (it goes back in the query string); the
        label is prose.
        """
        Module = request.env["ir.module.module"]
        if not Module.has_access("read"):
            return []
        env = request.env
        defining = {
            env[name]._original_module
            for name in env.registry
            if not env[name]._abstract
        }
        modules = Module.search(
            [("state", "=", "installed"), ("name", "in", sorted(defining))],
            order="shortdesc, name",
        )
        return [(module.name, alias_prose(module.shortdesc or module.name)) for module in modules]
