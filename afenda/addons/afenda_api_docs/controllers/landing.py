import re

from odoo import http
from odoo.http import request

# A leading version segment, as the web client's documentation_link widget
# concatenates it ("/docs/" + serverVersion + path). Accepted and ignored:
# the generated documentation is not versioned. Same forms the prose
# aliaser strips from a documentation URL (aliasing.py): "19.0", "saas-18.4",
# "latest", "master". Anything else is part of the page path.
_VERSION_SEGMENT = re.compile(r"^(?:\d+\.\d+|latest|master|saas-[\d.]+)$")


def _guide_xmlid(subpath):
    """Map a `/docs/<subpath>` URL onto the generated guide template it names.

    Drops a leading version segment and a trailing `.html` first, so both
    link shapes in the product - `/docs/19.0/applications/general/users.html`
    from the widget and `/docs/applications/general/users.html` hand-written
    - reach `guide_applications_general_users`. The rest mirrors
    `afenda/tools/build_docs.py:slug_for` (same `/` and `.` folding; it
    strips `.md` where this strips `.html`), duplicated rather than
    imported: that module is repo dev tooling invoked with
    `python -m afenda.tools.build_docs`, not part of the installed addon,
    and nothing guarantees the repo root is on `sys.path` at runtime.
    """
    first, sep, rest = subpath.partition("/")
    if sep and _VERSION_SEGMENT.match(first):
        subpath = rest
    subpath = subpath.removesuffix(".html")
    slug = subpath.replace("/", "_").replace(".", "_")
    return "afenda_api_docs.guide_%s" % slug


class AfendaDocsController(http.Controller):
    # The catch-all is not decoration: dozens of real in-product links point
    # at `/docs/applications/...` (`grep -rIoh "[\"'(]/docs/[A-Za-z0-9/_.#-]*"
    # addons/ odoo/` finds the hand-written ones, e.g.
    # `addons/auth_totp/views/templates.xml:12`). Those are only the
    # literal hrefs. Every Settings help icon that uses the
    # `documentation_link` widget builds its URL at runtime by
    # concatenating the server version in
    # (`addons/web/static/src/views/widgets/documentation_link/documentation_link.js:29`:
    # `return "/docs/" + serverVersion + this.props.path;`), so on a
    # released 19.0 server that widget really does request
    # `/docs/19.0/applications/...` - a `grep` for the literal string
    # `/docs/19.0/` finds nothing only because the version is never written
    # as text anywhere in this tree, not because no request ever carries
    # it. An earlier version of this comment conflated those two claims and
    # said the pattern "has zero occurrences ... since the rebrand's
    # `docs_link` rule already strips the version"; that was false, and is
    # corrected here.
    #
    # Both link shapes reach a guide when one is generated for the page:
    # `_guide_xmlid` drops the widget's version segment and the `.html`
    # suffix before folding the path into a template id, so the runtime
    # widget's `/docs/19.0/applications/general/users.html` and the
    # hand-written `/docs/applications/general/users.html`
    # (`addons/auth_totp/views/templates.xml:12`) both render
    # `guide_applications_general_users`, the id
    # `afenda/tools/build_docs.py:slug_for` gives
    # `applications/general/users.md`. An earlier version of this comment
    # recorded that neither shape reached the guide; tests/test_guides.py
    # now pins both. Only one guide is generated so far, so most in-product
    # links still name no guide and take the redirect below.
    #
    # This single route answers `/docs` (the landing page) and every
    # `/docs/<subpath>` (a generated guide, when one exists for that
    # subpath). A subpath naming no guide redirects to `/docs` instead of
    # 404ing or rendering the landing page inline at the guide's own URL:
    # the latter is the masquerade to avoid (a URL claiming to be a guide
    # that silently is not), but 404 would be honest and still hostile
    # while most subpaths simply have no guide generated yet. A redirect is
    # honest (the browser's address bar visibly changes) and usable.
    @http.route(
        ["/docs", "/docs/<path:subpath>"],
        type="http", auth="public", website=False, sitemap=False,
    )
    def docs_landing(self, subpath=None, **kwargs):
        if subpath is None:
            return request.render("afenda_api_docs.landing", {})
        xmlid = _guide_xmlid(subpath)
        if request.env.ref(xmlid, raise_if_not_found=False) is None:
            return request.redirect("/docs")
        # `no_footer`: same reasoning as `views/landing.xml` - this route is
        # `website=False`, so `request.is_frontend` never turns True and
        # `portal`'s footer-injected language selector 500s on the missing
        # `frontend_languages` value. Guides are generated from Markdown and
        # never set this themselves, so it is supplied here instead.
        return request.render(xmlid, {"no_footer": True})
