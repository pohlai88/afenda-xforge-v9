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
    # Only one guide (`guide_applications_general_users`) is generated so
    # far, and `_guide_xmlid` above cannot reach even that one, for two
    # separate reasons. It folds a subpath into a template id by replacing
    # `/` and `.` with `_` without stripping either a leading version
    # segment or a trailing `.html`. The runtime widget's URL,
    # `/docs/19.0/applications/general/users.html`, folds to
    # `guide_19_0_applications_general_users_html`; the hand-written
    # literal, `/docs/applications/general/users.html`
    # (`addons/auth_totp/views/templates.xml:12`, `.html` still present),
    # folds to `guide_applications_general_users_html`. Neither matches the
    # shipped id `guide_applications_general_users`, which
    # `afenda/tools/build_docs.py:slug_for` produces because it strips a
    # trailing `.md` (never `.html`) from a committed Markdown filename and
    # never sees a version segment at all, since it walks the source tree
    # rather than a URL. So no in-product link, of either shape, reaches
    # the one guide that exists today; every one of them redirects to
    # `/docs` instead. Nothing 404s or 500s because of this - the redirect
    # below covers it - so this is a routing gap to fix later, not an
    # outage now. Making `_guide_xmlid` version- and suffix-tolerant is
    # follow-up work with its own brief; it is not done here.
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
