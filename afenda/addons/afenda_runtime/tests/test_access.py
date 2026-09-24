from lxml import html as lxml_html

from odoo.tests import HttpCase, tagged

# Written out rather than built from BRAND, so a change to the encoding or the
# product name fails here instead of following along.
SUBJECT_QUERY = "subject=Access%20request%20%E2%80%94%20AFENDA%20xForge"


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
        for email, location in (
            ("hello@example.com", "mailto:hello@example.com?" + SUBJECT_QUERY),
            # `+` must be escaped, or dropping `quote` would go unnoticed.
            ("a+b@example.com", "mailto:a%2Bb@example.com?" + SUBJECT_QUERY),
        ):
            with self.subTest(email=email):
                self.env.company.email = email
                r = self.url_open("/request-access", allow_redirects=False)
                self.assertEqual(r.status_code, 303)
                self.assertEqual(r.headers["Location"], location)

    def test_request_access_without_email_explains(self):
        self.env.company.email = False
        r = self.url_open("/request-access", allow_redirects=False)
        self.assertEqual(r.status_code, 200)
        self.assertIn("The grove is by invitation.", r.text)
        self.assertIn("Ask your administrator to invite you.", r.text)
        # One of the logged-out pages, so it wears their poster: the auth body
        # class (afenda_brand's login_layout), the inline bear, and the
        # sentence as the page's one h1.
        doc = lxml_html.fromstring(r.text)
        self.assertIn("o_afenda_login", (doc.body.get("class") or "").split(),
                      "/request-access is not on web.login_layout")
        self.assertEqual(len(doc.find_class("o_afenda_auth_hero")), 1, "the bear is missing")
        titles = doc.xpath("//h1")
        self.assertEqual([t.text_content().strip() for t in titles],
                         ["The grove is by invitation."])
        # The page's one action is the way back to sign in.
        back = doc.find_class("o_afenda_auth_back")
        self.assertEqual([b.get("href") for b in back], ["/web/login"], "no way back to sign in")
        self.assertEqual(len(doc.find_class("o_afenda_auth_request")), 1,
                         "the moss skin's hook is missing")
        # disable_footer: no "Manage Databases" for someone without an account.
        self.assertNotIn("/web/database/manager", r.text)

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
