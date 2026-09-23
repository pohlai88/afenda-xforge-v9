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

    def test_settings_help_paths_do_not_404_before_the_guides_land(self):
        # What the documentation_link widget emits. Until Task 8 these fall
        # through to the landing page; they must never 404.
        res = self.url_open("/docs/19.0/applications/finance/accounting.html")
        self.assertEqual(res.status_code, 200)
