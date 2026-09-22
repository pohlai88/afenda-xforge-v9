import base64
import io
import re

from PIL import Image

from odoo.tests import HttpCase, tagged
from odoo.tools import file_open

from ..brand import BRAND

ODOO_TELLS = ("odoo.com", "Powered by Odoo", "odoo_logo", "Odoo S.A.")


@tagged("post_install", "-at_install")
class TestBranding(HttpCase):
    """What a normal user sees must say AFENDA, never Odoo."""

    def test_login_page_is_branded(self):
        html = self.url_open("/web/login").text
        self.assertIn("<title>AFENDA xForge</title>", html.replace("\n", ""))
        self.assertIn("/afenda_brand/static/img/favicon.ico", html)
        self.assertIn("AFENDA xForge", html)
        for tell in ODOO_TELLS:
            self.assertNotIn(tell, html, f"login page still shows {tell!r}")

    def test_webclient_page_is_branded(self):
        self.authenticate("admin", "admin")
        html = self.url_open("/odoo").text
        self.assertIn("<title>AFENDA xForge</title>", html.replace("\n", ""))
        self.assertNotIn("Powered by Odoo", html)
        # disable_odoo_online drops the odoo.com entries from the user menu;
        # make sure its code actually ships in the web client bundle.
        hrefs = re.findall(r'src="(/web/assets/[^"]+web\.assets_web[^"]*\.js)"', html)
        self.assertTrue(hrefs, "web.assets_web script not linked from /odoo")
        js = self.url_open(hrefs[0]).text
        for item in ("documentation", "support", "odoo_account"):
            self.assertIn(f'.remove("{item}")', js, f"user menu item {item!r} is not removed")

    def test_pwa_manifest_is_branded(self):
        manifest = self.url_open("/web/manifest.webmanifest").json()
        self.assertEqual(manifest["name"], BRAND["product"])
        self.assertEqual(manifest["short_name"], BRAND["short"])
        self.assertEqual(manifest["theme_color"].upper(), BRAND["primary"])
        self.assertNotIn("odoo", str(manifest.get("name", "")).lower())
        icons = [icon["src"] for icon in manifest["icons"]]
        self.assertTrue(icons, "manifest lists no icons")
        for src in icons:
            self.assertNotIn("odoo", src.lower(), f"manifest still serves an Odoo icon: {src}")
            self.assertEqual(self.url_open(src).status_code, 200)

    def _logo_size(self, b64):
        # Odoo re-encodes uploaded images, so compare dimensions, not bytes.
        return Image.open(io.BytesIO(base64.b64decode(b64))).size

    def test_company_defaults(self):
        company = self.env.ref("base.main_company")
        with file_open("afenda_brand/static/img/logo.png", "rb") as f:
            expected_size = Image.open(io.BytesIO(f.read())).size
        self.assertEqual(self._logo_size(company.logo), expected_size)
        self.assertEqual(company.name, BRAND["short"])
        self.assertTrue(company.favicon)
        self.assertEqual(company.email_primary_color.upper(), BRAND["primary"])
        new_company = self.env["res.company"].create({"name": "Second"})
        self.assertEqual(self._logo_size(new_company.logo), expected_size, "new companies get the AFENDA logo")

    def test_system_bot_is_branded(self):
        bot = self.env.ref("base.partner_root")
        self.assertEqual(bot.name, BRAND["bot"])
        users = self.env["res.users"].with_context(active_test=False).search([])
        self.assertTrue(all(u.odoobot_state == "disabled" for u in users))
        new_user = self.env["res.users"].create({"name": "Lee", "login": "lee@example.com"})
        self.assertEqual(new_user.odoobot_state, "disabled", "new users never get the Odoo onboarding chat")
        bot_messages = self.env["mail.message"].search(
            [("author_id", "=", bot.id), ("model", "=", "discuss.channel")]
        )
        for message in bot_messages:
            self.assertNotIn("odoo", (message.body or "").lower(), "bot message still mentions Odoo")

    def test_config_parameters(self):
        icp = self.env["ir.config_parameter"].sudo()
        self.assertEqual(icp.get_param("web.web_app_name"), BRAND["product"])
        self.assertEqual(icp.get_param("pwa.manifest.short_name"), BRAND["short"])

    def test_backend_theme_uses_brand_colors_and_fonts(self):
        self.authenticate("admin", "admin")
        html = self.url_open("/odoo").text
        hrefs = re.findall(r'href="(/web/assets/[^"]+web\.assets_web[^"]*\.css)"', html)
        self.assertTrue(hrefs, "web.assets_web stylesheet not linked from /odoo")
        css = self.url_open(hrefs[0]).text.lower()
        self.assertIn(BRAND["primary"].lower(), css)
        self.assertIn("source sans 3", css)
        self.assertIn("/afenda_brand/static/fonts/sourcesans3-vf.ttf", css)
        self.assertNotIn("#714b67", css, "Odoo enterprise purple must not survive")
        # html_editor hardcodes the community purple in its table picker; our
        # override must come later in the bundle so it wins.
        purple = css.rfind("#71639e")
        override = css.find(".o-we-tablepicker .o-we-cell.active{background-color: #1e3a8a")
        self.assertGreater(override, purple, "table picker override must follow the hardcoded purple")
        for match in re.finditer(r"([^{}]+)\{[^{}]*#71639e", css):
            self.assertIn(".o-we-tablepicker", match.group(1), f"unexpected Odoo purple in rule {match.group(1)!r}")
