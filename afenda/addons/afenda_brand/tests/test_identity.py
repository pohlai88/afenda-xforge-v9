import re

from odoo.tests import HttpCase, tagged

TELLS = re.compile(r"\bOdoo\b|odoo\.com|OdooBot|/odoo/|Odoo S\.A\.")


@tagged("post_install", "-at_install")
class TestIdentity(HttpCase):
    """No Odoo identity on any surface a user or their email client sees."""

    def assertClean(self, text, where):
        found = sorted(set(TELLS.findall(text)))
        self.assertFalse(found, f"{where} still shows {found}")

    def test_public_pages(self):
        for url in ("/web/login", "/web/database/manager", "/web/manifest.webmanifest"):
            self.assertClean(self.url_open(url).text, url)

    def test_app_prefix_serves_webclient_and_old_prefix_is_gone(self):
        self.authenticate("admin", "admin")
        page = self.url_open("/app")
        self.assertEqual(page.status_code, 200)
        self.assertIn("<title>AFENDA xForge</title>", page.text.replace("\n", ""))
        self.assertClean(page.text, "/app")
        self.assertEqual(self.url_open("/odoo", allow_redirects=False).status_code, 404)

    def test_notification_email_body(self):
        partner = self.env["res.partner"].create({"name": "Crawl Recipient", "email": "crawl@example.com"})
        record = self.env["res.partner"].create({"name": "Crawl Record"})
        record.message_post(
            body="identity check",
            partner_ids=partner.ids,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        mail = self.env["mail.mail"].search([("recipient_ids", "in", partner.ids)], order="id desc", limit=1)
        self.assertTrue(mail, "no outgoing mail was queued")
        self.assertClean(mail.body_html, "notification email")

    def test_report_html(self):
        report = self.env.ref("web.action_report_externalpreview")
        html, _ = self.env["ir.actions.report"]._render_qweb_html(report, self.env.company.ids)
        self.assertClean(html.decode(), "external layout preview report")

    def test_translations_for_a_loaded_language(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        self.env["ir.module.module"].search([("name", "=", "base")])._update_translations("fr_FR")
        # Odoo 16+ stores translations on the fields themselves; check a known string.
        menu = self.env.ref("base.menu_administration").with_context(lang="fr_FR")
        self.assertClean(menu.name, "fr_FR menu name")
