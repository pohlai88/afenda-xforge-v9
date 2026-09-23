from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestInviteOnly(HttpCase):
    """The ERP is invitation-only, and /request-access reaches the tenant.

    An HttpCase, so an Odoo BaseCase: a plain unittest class would be
    discovered and then silently dropped (odoo/tests/tag_selector.py:88-90).
    """

    def test_signup_is_closed(self):
        self.assertEqual(
            self.env["ir.config_parameter"].sudo().get_param("auth_signup.invitation_scope"),
            "b2b",
        )
        # Without a token, /web/signup raises NotFound unless the scope is b2c
        # (addons/auth_signup/controllers/main.py:43-44, :132).
        self.assertEqual(self.url_open("/web/signup").status_code, 404)

    def test_request_access_mails_the_company(self):
        self.env.company.email = "hello@example.com"
        r = self.url_open("/request-access", allow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertTrue(r.headers["Location"].startswith("mailto:hello@example.com?subject="))

    def test_request_access_without_email_explains(self):
        self.env.company.email = False
        r = self.url_open("/request-access", allow_redirects=False)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Access to AFENDA xForge is by invitation.", r.text)

    def test_request_access_rejects_a_malformed_email(self):
        # email_normalize alone does not reject these (odoo/tools/mail.py:812-845):
        # it returns 'x@y.z' for the first (the "Bcc:" reads as an RFC 5322
        # group), '@x.y' for the second, and the third unchanged, which as a
        # mailto: address would add a Bcc hfield. None may become a redirect.
        for email in (
            "not an email\r\nBcc: x@y.z",
            "a@b.c?cc=evil@x.y",
            "a?bcc=evil@x.y",
        ):
            with self.subTest(email=email):
                self.env.company.email = email
                r = self.url_open("/request-access", allow_redirects=False)
                self.assertEqual(r.status_code, 200)
                self.assertNotIn("Location", r.headers)
