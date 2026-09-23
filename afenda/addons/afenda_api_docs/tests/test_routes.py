from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestDocsRoutes(HttpCase):
    def test_landing_is_public_and_branded(self):
        res = self.url_open("/docs")
        self.assertEqual(res.status_code, 200)
        self.assertIn("AFENDA", res.text)

    def test_landing_carries_no_odoo_identity(self):
        res = self.url_open("/docs")
        for tell in ("Odoo", "odoo.com"):
            self.assertNotIn(tell, res.text)

    def test_guide_url_renders_its_guide(self):
        # "applications/general/users.md" -> template id
        # "guide_applications_general_users", per build_docs.py:slug_for.
        res = self.url_open("/docs/applications/general/users")
        self.assertEqual(res.status_code, 200)
        self.assertIn("<h1>Users and access rights</h1>", res.text)

    def test_unknown_subpath_404s(self):
        # This used to be the shape of a Settings help icon link
        # (`/docs/19.0/applications/finance/accounting.html`) that a prior
        # revision of this controller deliberately let fall through to the
        # landing page, before any guide existed to render. Now that guides
        # land (this module), a subpath naming no guide must 404 instead of
        # masquerading as the landing page — a stale or broken link should
        # be visible, not silently hidden. Routing those specific widget
        # links to their real guides is future work, not this task's.
        res = self.url_open("/docs/19.0/applications/finance/accounting.html")
        self.assertEqual(res.status_code, 404)
