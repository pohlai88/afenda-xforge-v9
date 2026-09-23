from odoo import http
from odoo.http import request


def _guide_xmlid(subpath):
    """Map a `/docs/<subpath>` URL onto the generated guide template it names.

    Mirrors `afenda/tools/build_docs.py:slug_for` (same `/` and `.` folding),
    duplicated rather than imported: that module is repo dev tooling invoked
    with `python -m afenda.tools.build_docs`, not part of the installed
    addon, and nothing guarantees the repo root is on `sys.path` at runtime.
    `slug_for` also strips a trailing `.md`, which a URL never carries, so
    the two are otherwise identical.
    """
    slug = subpath.replace("/", "_").replace(".", "_")
    return "afenda_api_docs.guide_%s" % slug


class AfendaDocsController(http.Controller):
    # The catch-all is not decoration: `117` Settings help icons point at
    # `/docs/19.0/applications/...` and this single route answers both
    # `/docs` (the landing page) and every `/docs/<subpath>` (a generated
    # guide, when one exists for that subpath). A subpath that does not name
    # a guide 404s rather than silently rendering the landing page, so a
    # broken or stale link is visible instead of masqueraded.
    @http.route(
        ["/docs", "/docs/<path:subpath>"],
        type="http", auth="public", website=False, sitemap=False,
    )
    def docs_landing(self, subpath=None, **kwargs):
        if subpath is None:
            return request.render("afenda_api_docs.landing", {})
        xmlid = _guide_xmlid(subpath)
        if request.env.ref(xmlid, raise_if_not_found=False) is None:
            raise request.not_found()
        # `no_footer`: same reasoning as `views/landing.xml` - this route is
        # `website=False`, so `request.is_frontend` never turns True and
        # `portal`'s footer-injected language selector 500s on the missing
        # `frontend_languages` value. Guides are generated from Markdown and
        # never set this themselves, so it is supplied here instead.
        return request.render(xmlid, {"no_footer": True})
