import base64
import io
import re
from pathlib import Path

from PIL import Image

from odoo.tests import HttpCase, tagged
from odoo.tools import config, file_open

from odoo.addons.afenda_brand.brand import BRAND, read_static
from odoo.addons.afenda_brand.hooks import (
    BLACKHOLE_URL,
    ODOO_SA_ENDPOINT_PARAMS,
    block_odoo_services,
)

ODOO_TELLS = ("odoo.com", "Powered by Odoo", "odoo_logo", "Odoo S.A.")

# Every Odoo S.A. host named in upstream code (odoo/ and addons/: .py, .xml,
# .js, .scss; tests excluded), reviewed against the self-hosted policy in
# afenda/SPEC.md §5. When an upstream merge adds a host,
# test_upstream_odoo_hosts_are_reviewed fails: decide how AFENDA blocks it,
# record that in SPEC.md, then add it here.
REVIEWED_ODOO_HOSTS = frozenset({
    # Links shown to users and example placeholders, no call-home
    "odoo.com", "www.odoo.com", "apps.odoo.com", "nightly.odoo.com",
    "mycompany.odoo.com", "yourcompany.odoo.com", "islamabadvendor.odoo.com", "punjabpartner.odoo.com",
    # Blocked by an ir.config_parameter endpoint (hooks.ODOO_SA_ENDPOINT_PARAMS)
    "iap.odoo.com", "iap-services.odoo.com", "iap-services-test.odoo.com",
    "partner-autocomplete.odoo.com", "sms.api.odoo.com", "iap-snailmail.odoo.com",
    "media-api.odoo.com", "olg.api.odoo.com", "website.api.odoo.com",
    # Disabled records (hooks.block_odoo_services) or publisher warranty (OCA)
    "accounts.odoo.com", "services.odoo.com",
    # Fetched by browsers or mail clients: CSP and the network layer (README §3-4)
    "fonts.odoocdn.com", "download.odoocdn.com",
    # Only after an explicit opt-in, and blocked by the network layer: VIES
    # checks (a company enables "Verify VAT Numbers"), mail OAuth proxy
    # (Community refuses it), payment onboarding, EDI proxy registration, IoT box
    "vies.api.odoo.com", "vies.test.odoo.com",
    "gmail.api.odoo.com", "outlook.api.odoo.com",
    "stripe.api.odoo.com", "razorpay.api.odoo.com", "payu.api.odoo.com", "mercadopago.api.odoo.com",
    "peppol.api.odoo.com", "peppol.test.odoo.com", "pdp.odoo.com", "pdp.api.odoo.com", "pdp.test.odoo.com",
    "nemhandel.api.odoo.com", "nemhandel.test.odoo.com",
    "l10n-my-edi.api.odoo.com", "l10n-my-edi.test.odoo.com", "l10n-it-edi.api.odoo.com",
    "l10n-in-edi.api.odoo.com", "l10n-in-edi-demo.api.odoo.com",
    "l10n-gr-edi.api.odoo.com", "l10n-gr-edi.test.odoo.com",
    "iot-proxy.odoo.com",
})


@tagged("post_install", "-at_install")
class TestBranding(HttpCase):
    """What a normal user sees must say AFENDA, never Odoo."""

    def test_login_page_is_branded(self):
        html = self.url_open("/web/login").text
        self.assertIn("<title>AFENDA xForge</title>", html.replace("\n", ""))
        self.assertIn("/afenda_brand/static/img/favicon.ico", html)
        for tell in ODOO_TELLS:
            self.assertNotIn(tell, html, f"login page still shows {tell!r}")

    def test_webclient_is_branded(self):
        self.authenticate("admin", "admin")
        html = self.url_open("/odoo").text
        self.assertIn("<title>AFENDA xForge</title>", html.replace("\n", ""))
        self.assertNotIn("Powered by Odoo", html)

        # disable_odoo_online drops the odoo.com entries from the user menu;
        # make sure its code actually ships in the web client bundle.
        scripts = re.findall(r'src="(/web/assets/[^"]+/web\.assets_web\.min\.js)"', html)
        self.assertTrue(scripts, "web.assets_web script not linked from /odoo")
        js = self.url_open(scripts[0]).text
        for item in ("documentation", "support", "odoo_account"):
            self.assertIn(f'.remove("{item}")', js, f"user menu item {item!r} is not removed")

        # The screen bundle, not web.assets_web_print which is linked first.
        hrefs = re.findall(r'href="(/web/assets/[^"]+/web\.assets_web(?:\.rtl)?\.min\.css)"', html)
        self.assertTrue(hrefs, "web.assets_web stylesheet not linked from /odoo")
        css = self.url_open(hrefs[0]).text.lower()
        self.assertIn(BRAND["primary"].lower(), css)
        self.assertIn("source sans 3", css)
        self.assertIn("/afenda_brand/static/fonts/sourcesans3-vf.woff2", css)
        self.assertNotIn("#714b67", css, "Odoo enterprise purple must not survive")
        # html_editor hardcodes the community purple in its table picker; our
        # override must come later in the bundle so it wins.
        purple = css.rfind("#71639e")
        override = css.find(".o-we-tablepicker .o-we-cell.active{background-color: #1e3a8a")
        self.assertGreater(override, purple, "table picker override must follow the hardcoded purple")
        for match in re.finditer(r"([^{}]+)\{[^{}]*#71639e", css):
            self.assertIn(".o-we-tablepicker", match.group(1), f"unexpected Odoo purple in rule {match.group(1)!r}")

    def test_pwa_manifest_is_branded(self):
        manifest = self.url_open("/web/manifest.webmanifest").json()
        self.assertEqual(manifest["name"], BRAND["product"])
        self.assertEqual(manifest["short_name"], BRAND["short"])
        self.assertEqual(manifest["theme_color"].upper(), BRAND["primary"])
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
        favicon = read_static("img/favicon.ico")
        new_company = self.env["res.company"].create({"name": "Second"})
        self.assertEqual(self._logo_size(new_company.logo), expected_size, "new companies get the AFENDA logo")
        for record in (company, new_company):
            self.assertEqual(record.favicon, favicon, f"{record.name} does not use the AFENDA favicon")
            self.assertEqual(record.primary_color.upper(), BRAND["primary"])
            # mail: email_primary_color is the button text, email_secondary_color the button.
            self.assertEqual(record.email_primary_color.upper(), "#FFFFFF")
            self.assertEqual(record.email_secondary_color.upper(), BRAND["primary"])

    def test_system_bot_is_branded(self):
        bot = self.env.ref("base.partner_root")
        self.assertEqual(bot.name, BRAND["bot"])
        users = self.env["res.users"].with_context(active_test=False).search([])
        self.assertTrue(all(u.odoobot_state == "disabled" for u in users))
        new_user = self.env["res.users"].create({"name": "Lee", "login": "lee@example.com"})
        self.assertEqual(new_user.odoobot_state, "disabled", "new users never get the Odoo onboarding chat")
        welcome = self.env.ref("mail.module_install_notification")
        self.assertEqual(welcome.subject, f"Welcome to {BRAND['product']}!")
        bot_messages = self.env["mail.message"].search(
            [("author_id", "=", bot.id), ("model", "=", "discuss.channel")],
        )
        for message in bot_messages:
            text = f"{message.subject or ''} {message.body or ''}".lower()
            self.assertNotIn("odoo", text, "bot message still mentions Odoo")

    def test_odoo_services_are_blocked(self):
        icp = self.env["ir.config_parameter"].sudo()
        self.assertEqual(icp.get_param("web.web_app_name"), BRAND["product"])
        for key in ODOO_SA_ENDPOINT_PARAMS:
            self.assertEqual(icp.get_param(key), BLACKHOLE_URL, f"{key} still reaches Odoo S.A.")
        self.assertFalse(icp.get_param("iap_vies.endpoint"), "base_vat only accepts odoo.com VIES endpoints")

    def test_block_odoo_services(self):
        """The boot-time enforcement repairs drift and is a no-op otherwise."""
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("sms.endpoint", False)
        # Stand-ins for records that base_vat and auth_oauth would bring.
        cron = self.env["ir.cron"].create({
            "name": "VIES stand-in",
            "model_id": self.env.ref("base.model_res_partner").id,
            "state": "code",
            "code": "model",
        })
        self.env["ir.model.data"].create({
            "module": "base_vat", "name": "vies_iap_check_update", "model": "ir.cron", "res_id": cron.id,
        })
        block_odoo_services(self.env)
        self.assertEqual(icp.get_param("sms.endpoint"), BLACKHOLE_URL)
        self.assertFalse(cron.active, "the VIES cron must stay off")
        icp.set_param("sms.endpoint", "https://sms.example.com")
        block_odoo_services(self.env)
        self.assertEqual(icp.get_param("sms.endpoint"), "https://sms.example.com", "an admin's own endpoint is kept")

    def test_upstream_odoo_hosts_are_reviewed(self):
        host_re = re.compile(rb"https?://([a-z0-9.-]*odoo(?:cdn)?\.com)")
        hosts, scanned = set(), 0
        for root in map(Path, (config.root_path, config.addons_community_dir)):
            for path in root.rglob("*"):
                if path.suffix in {".py", ".xml", ".js", ".scss"} and "tests" not in path.relative_to(root).parts:
                    scanned += 1
                    hosts.update(h.decode() for h in host_re.findall(path.read_bytes()))
        self.assertGreater(scanned, 1000, "upstream source not found: the scan checked nothing")
        unreviewed = hosts - REVIEWED_ODOO_HOSTS
        self.assertFalse(unreviewed, f"new Odoo S.A. hosts in upstream code, review them: {sorted(unreviewed)}")
