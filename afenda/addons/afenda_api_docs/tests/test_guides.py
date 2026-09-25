from odoo.tests import HttpCase, tagged

TITLE = "<h1>Users and access rights</h1>"


@tagged("post_install", "-at_install")
class TestGuideRoutes(HttpCase):
    def assertRendersTheGuide(self, url):
        res = self.url_open(url, allow_redirects=False)
        self.assertEqual(res.status_code, 200, url)
        self.assertIn(TITLE, res.text, url)

    def assertRedirectsToTheIndex(self, url):
        res = self.url_open(url, allow_redirects=False)
        self.assertEqual(res.status_code, 303, url)
        self.assertEqual(res.headers["Location"], "/docs", url)

    def test_hand_written_link_shape_renders_the_guide(self):
        # The literal shape in-product links carry, `.html` included
        # (e.g. addons/auth_totp/views/templates.xml:12).
        self.assertRendersTheGuide("/docs/applications/general/users.html")

    def test_documentation_link_widget_shape_renders_the_guide(self):
        # What the widget builds at runtime: "/docs/" + serverVersion + path
        # (addons/web/static/src/views/widgets/documentation_link/documentation_link.js:29).
        self.assertRendersTheGuide("/docs/19.0/applications/general/users.html")

    def test_every_version_form_is_accepted_and_ignored(self):
        # The generated documentation is not versioned; the segment only
        # exists because the widget concatenates one. Same set of forms the
        # prose aliaser accepts in a documentation URL (aliasing.py).
        for version in ("19.0", "18.0", "saas-18.4", "latest", "master"):
            self.assertRendersTheGuide(f"/docs/{version}/applications/general/users.html")
            self.assertRendersTheGuide(f"/docs/{version}/applications/general/users")

    def test_an_unwritten_versioned_page_still_redirects_to_the_index(self):
        # The redirect fallback stays (see test_routes.py): a missing guide
        # is never a 404 and never leaves the origin, versioned or not.
        self.assertRedirectsToTheIndex("/docs/19.0/applications/finance/nothing_here.html")
        self.assertRedirectsToTheIndex("/docs/19.0")

    def test_a_segment_that_is_not_a_version_is_not_stripped(self):
        # Only a version-shaped first segment is ignored; anything else is
        # part of the page path, which then names no guide.
        self.assertRedirectsToTheIndex("/docs/general/applications/general/users.html")
        self.assertRedirectsToTheIndex("/docs/19/applications/general/users.html")

    def _guide_xmlid_for(self, record, name):
        self.env["ir.model.data"].create({
            "module": "afenda_api_docs",
            "name": f"guide_{name}",
            "model": record._name,
            "res_id": record.id,
        })

    def test_a_guide_xmlid_on_a_non_view_record_is_not_rendered(self):
        # Only a QWeb view may be rendered from a URL; any other record
        # that happens to carry a `guide_*` xmlid redirects like a missing page.
        partner = self.env["res.partner"].create({"name": "Not a guide"})
        self._guide_xmlid_for(partner, "not_a_view")
        self.assertRedirectsToTheIndex("/docs/not_a_view")

    def test_a_guide_xmlid_on_a_non_qweb_view_is_not_rendered(self):
        view = self.env["ir.ui.view"].create({
            "name": "not a guide",
            "type": "form",
            "model": "res.partner",
            "arch": "<form><field name='name'/></form>",
        })
        self._guide_xmlid_for(view, "form_view")
        self.assertRedirectsToTheIndex("/docs/form_view")
