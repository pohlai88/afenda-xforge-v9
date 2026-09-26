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
# uppercase letter - is refused before the filesystem is ever touched, so a
# path trick has nothing to work with even before the parent-directory
# check below.
_AREA_RE = re.compile(r"^[a-z0-9_]+$")


def _committed_areas():
    """Sorted stems of every committed OpenAPI asset area on disk."""
    return sorted(path.stem for path in _OPENAPI_DIR.glob("*.json"))


class AfendaApiController(http.Controller):
    # auth='user' on both routes: the document lists every model and field the
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

    # auth='user': same reasoning as /docs/openapi.json - each area's
    # document lists every model and field an integrator can call, which is
    # per-user information disclosure even though the committed bytes
    # themselves are the same for everyone (AFD-ARCH-CORR-0005 fixes the
    # document to base.user_admin at build time; this route does not
    # regenerate it per caller, it only gates *access* to the committed
    # file the same way the live document is gated).
    @http.route(
        "/docs/api/spec/<string:area>.json",
        type="http", auth="user", methods=["GET"], website=False, sitemap=False,
    )
    def docs_api_spec(self, area, **kwargs):
        """Serve one committed OpenAPI asset area's bytes, verbatim, from disk.

        Two independent checks stand between this route and the filesystem,
        because either one failing alone must not be enough to escape
        `_OPENAPI_DIR`: `_AREA_RE` refuses any `area` that is not
        `^[a-z0-9_]+$` (a dot, a slash - encoded or not - or a stray null
        byte all fail it, so `..%2fmanifest`, `%2e%2e` and
        `core.json%00` never even reach a path lookup), and the resolved
        file's parent must still equal `_OPENAPI_DIR` (defence in depth
        against anything the regex alone might miss). Only then is the file
        read - never through `area` used to build a path before both checks
        pass.
        """
        if not _AREA_RE.match(area):
            return request.not_found()
        path = (_OPENAPI_DIR / f"{area}.json").resolve()
        if path.parent != _OPENAPI_DIR or not path.is_file():
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
