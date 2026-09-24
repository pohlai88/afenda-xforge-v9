import re

from odoo.tests import HttpCase, tagged

# `title="odoo"` is its own shape: lowercase, so `\bOdoo\b` misses it, and it
# is what a tooltip shows on hover. The peer's product_lowercase_attr rule
# rewrote the one occurrence (addons/portal/views/portal_templates.xml); this
# is the guard that an upstream merge does not bring it back.
TELLS = re.compile(r"\bOdoo\b|odoo\.com|OdooBot|/odoo/|Odoo S\.A\.|title=[\"']odoo[\"']")


@tagged("post_install", "-at_install")
class TestIdentity(HttpCase):
    """No Odoo identity on any surface a user or their email client sees."""

    def assertClean(self, text, where):
        found = sorted(set(TELLS.findall(text)))
        self.assertFalse(found, f"{where} still shows {found}")

    def test_public_pages(self):
        for url in ("/web/login", "/web/database/manager", "/web/manifest.webmanifest"):
            self.assertClean(self.url_open(url).text, url)

    def test_portal_home(self):
        """The portal is the one logged-in surface a customer sees, and its
        footer is where "Powered by Odoo" and the lowercase `title="odoo"`
        tooltip lived. It needs a session: /my redirects to the login page
        otherwise, and a login page that is clean proves nothing about /my."""
        self.authenticate("admin", "admin")
        page = self.url_open("/my")
        self.assertEqual(page.status_code, 200)
        self.assertClean(page.text, "/my")

    def test_app_prefix_serves_webclient_and_old_prefix_is_gone(self):
        self.authenticate("admin", "admin")
        page = self.url_open("/app")
        self.assertEqual(page.status_code, 200)
        self.assertIn("<title>AFENDA xForge</title>", page.text.replace("\n", ""))
        self.assertClean(page.text, "/app")
        self.assertEqual(self.url_open("/odoo", allow_redirects=False).status_code, 404)

    def test_notification_email_body(self):
        # An internal recipient gets the "View" call to action, and the two
        # force_* flags switch the header and footer on, so one render covers
        # the CTA, the body face and the "Powered by" line.
        recipient = self.env["res.users"].create(
            {"name": "Crawl Recipient", "login": "crawl@example.com", "email": "crawl@example.com"}
        )
        partner = recipient.partner_id
        record = self.env["res.partner"].create({"name": "Crawl Record"})
        record.with_context(
            email_notification_force_header=True,
            email_notification_force_footer=True,
        ).message_post(
            body="identity check",
            partner_ids=partner.ids,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        mail = self.env["mail.mail"].search([("recipient_ids", "in", partner.ids)], order="id desc", limit=1)
        self.assertTrue(mail, "no outgoing mail was queued")
        body = mail.body_html
        self.assertClean(body, "notification email")
        # The AFENDA layout, not Odoo's: Ledger Blue on the CTA, the AFENDA
        # mark in the header row that now leads the mail (it moved out of the
        # footer's "Powered by" line, which is gone entirely), and none of the
        # three values only mail's own templates can emit.
        self.assertIn("#1E3A8A", body, "the CTA is not Ledger Blue")
        self.assertIn("logo_email_2x.png", body, "the header has no AFENDA mark")
        for tell in ("#875A7B", "#F1F1F1", "Verdana"):
            self.assertNotIn(tell, body, f"notification email still carries {tell!r}")

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

    def test_docs_route_answers_same_origin(self):
        # afenda_api_docs owns the content; this module only cares that the
        # rewritten documentation links resolve on this origin at all.
        self.assertEqual(self.url_open("/docs").status_code, 200)
        self.assertEqual(self.url_open("/docs/applications/sales.html").status_code, 200)
