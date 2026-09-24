from odoo.tests import TransactionCase, tagged
from odoo.tools import SQL

from odoo.addons import afenda_runtime

# The two paragraphs exactly as auth_signup stores them in the internal-user
# invitation: addons/auth_signup/data/mail_template_data.xml:53-56 after the
# XML import (which writes `<br/>`) and before the tenant colour tokens were
# rebranded (a noupdate record keeps the colour it was installed with, which is
# why the fix may not key on that attribute).
INDENT = " " * 24
MARKETING = (
    f"\n{INDENT}Never heard of AFENDA xForge? It’s an all-in-one business software"
    " loved by 12+ million users. It will considerably improve your experience at"
    " work and increase your productivity."
    f"\n{INDENT}<br/><br/>"
    f'\n{INDENT}Have a look at the <a href="https://www.nexuscanon.com/page/tour?'
    'utm_source=db&amp;utm_medium=auth" t-attf-style="color: '
    "{{object.company_id.email_secondary_color or '#875A7B'}};\">AFENDA xForge Tour</a>"
    " to discover the tool."
    f"\n{INDENT}<br/><br/>"
)
SIGN_OFF = f"\n{INDENT}Enjoy AFENDA xForge!"

# The same two paragraphs in French (addons/auth_signup/i18n/fr.po:632-640).
FR_MARKETING = (
    f"\n{INDENT}Vous ne connaissez pas encore AFENDA xForge ? C’est un logiciel de"
    " gestion tout-en-un, adopté par plus de 12 millions d’utilisateurs. Il vous"
    " permettra d’optimiser votre travail et de gagner en productivité."
    f"\n{INDENT}<br/><br/>"
    f'\n{INDENT}Découvrez-le en explorant le <a href="https://www.nexuscanon.com/'
    'page/tour?utm_source=db&amp;utm_medium=auth" t-attf-style="color: '
    "{{object.company_id.email_secondary_color or '#875A7B'}};\">Tour AFENDA xForge</a>."
    f"\n{INDENT}<br/><br/>"
)
FR_BUTTON = "Accepter l'invitation"
FR_SIGN_OFF = f"\n{INDENT}Profitez bien d'AFENDA xForge !"

AUTH_SIGNUP_TEMPLATES = (
    "auth_signup.set_password_email",
    "auth_signup.portal_set_password_email",
    "auth_signup.mail_template_user_signup_account_created",
    "auth_signup.mail_template_data_unregistered_users",
)


@tagged("post_install", "-at_install")
class TestInvitationMail(TransactionCase):
    """The invitation makes no claim the product cannot back, and links nowhere dead.

    A TransactionCase, so an Odoo BaseCase: a plain unittest class would be
    discovered and then silently dropped (odoo/tests/tag_selector.py:88-90).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = cls.env.ref("auth_signup.set_password_email")

    def _stored(self):
        self.template.flush_recordset(["body_html"])
        self.env.cr.execute(SQL(
            "SELECT body_html FROM mail_template WHERE id = %s", self.template.id,
        ))
        return self.env.cr.fetchone()[0]

    def _store(self, lang, body):
        self.template.flush_recordset(["body_html"])
        self.env.cr.execute(SQL(
            "UPDATE mail_template SET body_html = body_html || jsonb_build_object(%s, %s::text)"
            " WHERE id = %s",
            lang, body, self.template.id,
        ))
        self.template.invalidate_recordset(["body_html"])

    def _dirty(self, clean):
        # str(): Markup.replace would escape the inserted tags into text.
        self.assertIn(SIGN_OFF, clean)
        return str(clean).replace(SIGN_OFF, MARKETING + SIGN_OFF, 1)

    def _invitation_body(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Invited Colleague",
            "login": "invited.colleague@example.com",
            "email": "invited.colleague@example.com",
        })
        self.assertTrue(user._is_internal())
        # What _action_reset_password does before send_mail renders the body
        # (addons/auth_signup/models/res_users.py:165, :200).
        user.partner_id.signup_prepare(signup_type="signup")
        return self.template.with_context(create_user=True)._render_field(
            "body_html", user.ids, compute_lang=True,
        )[user.id]

    def test_invitation_has_no_marketing_and_keeps_the_invitation(self):
        body = str(self._invitation_body())
        self.assertNotIn("million users", body)
        self.assertNotIn("/page/tour", body)
        self.assertIn("/web/signup", body)
        self.assertIn("Accept invitation", body)
        self.assertIn("Enjoy AFENDA xForge!", body)

    def test_no_auth_signup_template_carries_the_lines(self):
        for xmlid in AUTH_SIGNUP_TEMPLATES:
            with self.subTest(template=xmlid):
                body = self.env.ref(xmlid).body_html or ""
                self.assertNotIn("million users", body)
                self.assertNotIn("/page/tour", body)

    def test_fix_removes_exactly_the_two_paragraphs(self):
        clean = self.template.body_html
        self.template.body_html = self._dirty(clean)
        self.assertIn("million users", self.template.body_html)

        afenda_runtime.strip_invitation_marketing(self.env)

        self.assertEqual(self.template.body_html, clean)

    def test_fix_is_idempotent(self):
        clean = self.template.body_html
        self._store("en_US", self._dirty(clean))

        self.assertEqual(afenda_runtime.strip_invitation_marketing(self.env), self.template)
        once = self._stored()
        self.assertFalse(afenda_runtime.strip_invitation_marketing(self.env))
        self.assertEqual(self._stored(), once)
        self.assertEqual(once["en_US"], clean)

    def test_fix_cleans_every_stored_language(self):
        # fr_FR is not active here: the fix reaches every stored value, not only
        # the languages an ORM write could address.
        clean = self.template.body_html
        fr_clean = (
            str(clean)
            .replace("Accept invitation", FR_BUTTON)
            .replace(SIGN_OFF, FR_SIGN_OFF)
        )
        self._store("fr_FR", fr_clean.replace(FR_SIGN_OFF, FR_MARKETING + FR_SIGN_OFF, 1))
        self.assertIn("12 millions", self._stored()["fr_FR"])

        afenda_runtime.strip_invitation_marketing(self.env)

        stored = self._stored()
        self.assertEqual(stored["fr_FR"], fr_clean)
        self.assertIn(FR_BUTTON, stored["fr_FR"])
        self.assertIn(FR_SIGN_OFF, stored["fr_FR"])
        self.assertEqual(stored["en_US"], clean)

    def test_language_loaded_later_is_cleaned(self):
        self.assertNotIn("fr_FR", self._stored())
        self.env["res.lang"]._activate_lang("fr_FR")
        # The path res.lang activation and the language wizard take
        # (odoo/addons/base/models/ir_module.py:893).
        self.env["ir.module.module"]._load_module_terms(["auth_signup"], ["fr_FR"])

        fr_body = self._stored()["fr_FR"]
        self.assertIn("Bonjour", fr_body)  # the French body did load
        self.assertNotIn("millions", fr_body)
        self.assertNotIn("/page/tour", fr_body)
        self.assertIn(FR_BUTTON, fr_body)
        self.assertIn(FR_SIGN_OFF, fr_body)
