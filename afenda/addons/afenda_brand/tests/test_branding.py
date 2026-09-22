import base64
import io
import re

from lxml import etree as lxml_etree
from lxml import html as lxml_html
from markupsafe import Markup
from PIL import Image

from odoo.tests import HttpCase, tagged
from odoo.tools import file_open, is_html_empty

from ..brand import BRAND
from ..hooks import _UPSTREAM_REPORT_FONT, _apply_company_branding

ODOO_TELLS = ("odoo.com", "Powered by Odoo", "odoo_logo", "Odoo S.A.")


@tagged("post_install", "-at_install")
class TestBranding(HttpCase):
    """What a normal user sees must say AFENDA, never Odoo."""

    def test_login_page_is_branded(self):
        html = self.url_open("/web/login").text
        self.assertIn("<title>AFENDA xForge</title>", html.replace("\n", ""))
        self.assertIn("/afenda_brand/static/img/favicon.ico", html)
        self.assertIn("AFENDA xForge", html)
        self.assertIn("o_afenda_login", html, "the login body class is missing")
        self.assertIn(BRAND["tagline"], html, "the login card is missing the tagline")
        # bg-100 and border-0 are !important utilities: while either is on the
        # card, login.scss cannot paint it whatever the selector or load order.
        card = re.search(r'<div[^>]*\bclass="([^"]*\bo_database_list\b[^"]*)"', html)
        self.assertTrue(card, "the login card was not rendered")
        # `border` is in the list for the opposite reason: re-adding it makes
        # Bootstrap's utility paint the edge, which turns the hairline rule in
        # login.scss into dead code and the assertion in
        # test_frontend_css_has_login_surface vacuous. login.scss owns the
        # border: `.o_afenda_login .o_database_list` (0-2-0, later in the
        # bundle) already outranks `.card` (0-1-0, no !important).
        for utility in ("bg-100", "border-0", "border"):
            self.assertNotIn(utility, card.group(1).split(), f"{utility} still overrides the card")
        for tell in ODOO_TELLS:
            self.assertNotIn(tell, html, f"login page still shows {tell!r}")

    def test_frontend_css_has_login_surface(self):
        html = self.url_open("/web/login").text
        hrefs = re.findall(r'href="(/web/assets/[^"]+web\.assets_frontend[^"]*\.css)"', html)
        self.assertTrue(hrefs, "web.assets_frontend stylesheet not linked from /web/login")
        css = self.url_open(hrefs[0]).text.lower()
        ground = re.search(r"\.o_afenda_login\s*\{([^}]*)\}", css)
        self.assertTrue(ground, "login.scss is not in the frontend bundle")
        self.assertIn(BRAND["paper"].lower(), ground.group(1), "the login ground is not AFENDA paper")
        card = re.search(r"\.o_afenda_login\s+\.o_database_list\s*\{([^}]*)\}", css)
        self.assertTrue(card, "the login card rule is not in the frontend bundle")
        self.assertIn("#fff", card.group(1), "the login card is not white")
        self.assertIn(BRAND["hairline"].lower(), card.group(1), "the login card has no hairline border")

    def test_webclient_page_is_branded(self):
        self.authenticate("admin", "admin")
        html = self.url_open("/app").text
        self.assertIn("<title>AFENDA xForge</title>", html.replace("\n", ""))
        self.assertNotIn("Powered by Odoo", html)
        # disable_odoo_online drops the odoo.com entries from the user menu;
        # make sure its code actually ships in the web client bundle.
        hrefs = re.findall(r'src="(/web/assets/[^"]+web\.assets_web[^"]*\.js)"', html)
        self.assertTrue(hrefs, "web.assets_web script not linked from /odoo")
        js = self.url_open(hrefs[0]).text
        for item in ("documentation", "support", "odoo_account"):
            self.assertIn(f'.remove("{item}")', js, f"user menu item {item!r} is not removed")

    def test_favicon_is_served_on_every_page(self):
        """web.layout resolves the shortcut icon through web_favicon's
        `_get_favicon()` before falling back to the AFENDA file. Regression: if
        that lookup is dropped the per-company favicon the install hook writes
        is never served; if it is wrong, the browser tab on /app gets a 404
        instead of an icon."""
        for url, authenticated in (("/web/login", False), ("/app", True)):
            if authenticated:
                self.authenticate("admin", "admin")
            html = self.url_open(url).text
            href = re.search(r'<link[^>]*rel="shortcut icon"[^>]*href="([^"]+)"', html)
            self.assertTrue(href, f"{url} links no shortcut icon")
            icon = self.url_open(href.group(1))
            self.assertEqual(icon.status_code, 200, f"{url}: {href.group(1)} is not served")
            self.assertTrue(icon.content, f"{url}: the favicon is empty")
            # Whatever the route, the bytes are the AFENDA favicon: the hook
            # wrote the same file onto every company.
            with file_open("afenda_brand/static/img/favicon.ico", "rb") as f:
                self.assertEqual(icon.content, f.read(), f"{url} serves a different favicon")

    def test_pwa_manifest_is_branded(self):
        manifest = self.url_open("/web/manifest.webmanifest").json()
        self.assertEqual(manifest["name"], BRAND["product"])
        self.assertEqual(manifest["short_name"], BRAND["short"])
        self.assertEqual(manifest["theme_color"].upper(), BRAND["primary"])
        self.assertNotIn("odoo", str(manifest.get("name", "")).lower())
        self.assertTrue(manifest["icons"], "manifest lists no icons")
        for icon in manifest["icons"]:
            src = icon["src"]
            self.assertNotIn("odoo", src.lower(), f"manifest still serves an Odoo icon: {src}")
            self.assertEqual(self.url_open(src).status_code, 200)
            # Without "maskable" Android crops the tile into a circle.
            self.assertIn("maskable", icon.get("purpose", ""), f"{src} is not maskable")

    def test_theme_meta_and_offline(self):
        self.authenticate("admin", "admin")
        html = self.url_open("/app").text
        self.assertIn(f'<meta name="theme-color" content="{BRAND["primary"]}"/>', html)
        # The offline page is served without any stylesheet, so its colors are
        # inline. Upstream's <style> keeps the Odoo purple; ours comes after it.
        offline = self.url_open("/app/offline").text
        self.assertIn(BRAND["primary"], offline)
        self.assertIn(BRAND["paper"], offline)
        self.assertIn(BRAND["ink"], offline)
        self.assertGreater(
            offline.rfind(BRAND["primary"]),
            offline.rfind("#714B67"),
            "the AFENDA offline style must follow the Odoo one to win",
        )

    def test_scoped_app_manifest(self):
        manifest = self.url_open(
            "/web/manifest.scoped_app_manifest?app_id=mail&path=/app/discuss"
        ).json()
        self.assertEqual(manifest["theme_color"].upper(), BRAND["primary"])
        self.assertEqual(manifest["background_color"].upper(), BRAND["paper"])
        # Recoloring rebuilds the response; the app scope must survive it.
        self.assertEqual(manifest["scope"], "/app/discuss")

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
        new_company = self.env["res.company"].create({"name": "Second"})
        self.assertEqual(self._logo_size(new_company.logo), expected_size, "new companies get the AFENDA logo")
        # mail reads these from the email: "primary" is the CTA button text,
        # "secondary" is the button fill. A blue-on-blue button is unreadable.
        for record in (company, new_company):
            self.assertEqual(record.email_secondary_color.upper(), BRAND["primary"])
            self.assertEqual(record.email_primary_color.upper(), "#FFFFFF")
        # Printed documents: the defaults reach companies created after install.
        self.assertEqual(new_company.font, "Source_Sans_3")
        self.assertEqual(
            new_company.external_report_layout_id,
            self.env.ref("web.external_layout_standard"),
        )
        self.assertEqual(new_company.primary_color.upper(), BRAND["ink"])
        self.assertEqual(new_company.secondary_color.upper(), BRAND["graphite"])

    def test_migration_reapplies_company_branding(self):
        """The 19.0.1.0.1 migration calls `_apply_company_branding` so that an
        existing database picks up a branding fix on `-u afenda_brand`;
        `post_init_hook` runs at install only and never would.

        Two companies, because the function has two jobs that pull against each
        other: repair what AFENDA got wrong, keep what the administrator chose.
        """
        # A company as an install from before both fixes left it.
        stale = self.env["res.company"].create({"name": "Stale"})
        stale.write({
            # The pre-inversion values: fill colour in the text field, ink in
            # the fill field.
            "email_primary_color": BRAND["primary"],
            "email_secondary_color": BRAND["ink"],
            # The pre-Task-4 document state: upstream font, no layout, no colours.
            "font": _UPSTREAM_REPORT_FONT,
            "external_report_layout_id": False,
            "primary_color": False,
            "secondary_color": False,
        })
        # A company an administrator has since configured.
        chosen = self.env["res.company"].create({"name": "Chosen"})
        boxed = self.env.ref("web.external_layout_boxed")
        chosen.write({
            "font": "Roboto",
            "primary_color": "#123456",
            "secondary_color": "#654321",
            "email_secondary_color": "#ABCDEF",
            "external_report_layout_id": boxed.id,
        })

        _apply_company_branding(self.env)

        # Regression: guard the two email colours on the upstream default alone
        # and #0F172A is not it, so the company is skipped forever -- every
        # upgrade re-ships the unreadable Ledger-Blue-on-ink CTA button that
        # the inversion fix was supposed to end.
        self.assertEqual(stale.email_secondary_color.upper(), BRAND["primary"])
        self.assertEqual(stale.email_primary_color.upper(), BRAND["on_primary"])
        # Regression: leave the branding body inside post_init_hook (or omit
        # the migration, or omit the version bump that makes it run) and the
        # document defaults never reach a company that already exists.
        self.assertEqual(stale.font, "Source_Sans_3")
        self.assertEqual(
            stale.external_report_layout_id,
            self.env.ref("web.external_layout_standard"),
        )
        self.assertEqual(stale.primary_color.upper(), BRAND["ink"])
        self.assertEqual(stale.secondary_color.upper(), BRAND["graphite"])

        # Regression: drop any of the guards -- or widen the replaceable set
        # past the exact superseded values -- and an upgrade silently reverts
        # an administrator's branding, which is worse than never applying ours.
        self.assertEqual(chosen.font, "Roboto")
        self.assertEqual(chosen.primary_color, "#123456")
        self.assertEqual(chosen.secondary_color, "#654321")
        self.assertEqual(chosen.email_secondary_color, "#ABCDEF")
        self.assertEqual(chosen.external_report_layout_id, boxed)

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

    def test_app_icons_are_branded(self):
        """The apps menu draws `web_icon_data`, a cached copy of the icon file
        taken when `web_icon` was last written
        (odoo/addons/base/models/ir_ui_menu.py:158-162). Rendering new tiles on
        disk does not touch it, so without the refresh step in post_init_hook an
        existing database keeps Odoo's teal hexagons for every root menu."""
        roots = self.env["ir.ui.menu"].sudo().with_context(active_test=False).search(
            [("parent_id", "=", False), ("web_icon", "!=", False)]
        )
        self.assertTrue(roots, "no root menu carries a web_icon")
        brand = {
            tuple(int(BRAND[k][i:i + 2], 16) for i in (1, 3, 5)): k
            for k in ("primary", "graphite")
        }
        checked = 0
        for menu in roots:
            # A three-part web_icon is a "built" icon (class,colour,background)
            # and stores no image at all; only the two-part `module,path` form
            # has web_icon_data.
            if len(menu.web_icon.split(",")) != 2 or not menu.web_icon_data:
                continue
            image = Image.open(io.BytesIO(base64.b64decode(menu.web_icon_data))).convert("RGBA")
            # Mid-top edge: inside the tile whatever the corner radius.
            pixel = image.getpixel((image.width // 2, 0))[:3]
            self.assertIn(
                pixel, brand,
                f"{menu.name}: {menu.web_icon} is not an AFENDA tile (top edge {pixel})",
            )
            checked += 1
        # This database installs few apps; Discuss plus the three base root
        # menus (Apps, Settings, Tests) are the floor.
        self.assertGreaterEqual(checked, 4, "too few image icons probed to prove anything")
        self.assertEqual(
            checked, len([m for m in roots if len(m.web_icon.split(",")) == 2]),
            "a root menu names an image icon but stores no web_icon_data",
        )
        # The apps menu also serves the SVG beside each PNG; #985184 is the
        # Odoo purple the upstream icon.svg files were drawn in.
        svg = self.url_open("/mail/static/description/icon.svg").text
        self.assertNotIn("#985184", svg, "the mail app icon is still Odoo artwork")
        self.assertIn(BRAND["primary"], svg, "the mail app icon is not a Ledger Blue tile")

    def test_empty_state_is_a_ledger_page(self):
        """Regression: without the backend.scss override the three empty-state
        helpers keep Odoo's smiling/neutral faces and folder drawings."""
        self.authenticate("admin", "admin")
        html = self.url_open("/app").text
        hrefs = re.findall(r'href="(/web/assets/[^"]+web\.assets_web[^"]*\.css)"', html)
        self.assertTrue(hrefs, "web.assets_web stylesheet not linked from /app")
        css = self.url_open(hrefs[0]).text
        self.assertEqual(self.url_open("/afenda_brand/static/img/empty_state.svg").status_code, 200)
        ours = css.rfind("/afenda_brand/static/img/empty_state.svg")
        self.assertGreater(ours, -1, "empty_state.svg never reaches the backend bundle")
        # Same specificity as upstream's rule, so only load order decides.
        for upstream in ("smiling_face.svg", "neutral_face.svg", "empty_folder.svg"):
            self.assertGreater(
                ours, css.rfind(upstream),
                f"the AFENDA empty state must follow the last {upstream} rule to win",
            )

    def test_effects_and_help_are_quiet(self):
        """Regression: drop effects.js and a saved record fires the rainbow man
        again; drop user_menu.js and the user menu has no Help at all, because
        disable_odoo_online removes upstream's (its `support` item) and nothing
        replaces it."""
        self.authenticate("admin", "admin")
        html = self.url_open("/app").text
        self.assertIn('"afenda_docs_url"', html, "session_info does not publish the docs url")
        self.assertIn(BRAND["docs_path"], html, "session_info carries the wrong docs url")
        js = self._webclient_js(html)
        self.assertIn("afenda_help", js, "the Help user-menu item is not in the bundle")
        self.assertIn("session.afenda_docs_url", js, "Help does not read the url from the session")
        # `force: true` is what lets a second registration replace web's own
        # "rainbow_man" (effect_service.js:58) instead of throwing on a
        # duplicate key; without it the AFENDA effect never takes.
        effect = js.rfind('"rainbow_man"')
        self.assertGreater(effect, -1, "no rainbow_man registration in the bundle")
        self.assertIn("force", js[effect:effect + 200], "the rainbow_man override is not forced")
        self.assertGreater(
            effect, js.find('effectRegistry.add("rainbow_man"'),
            "the AFENDA effect must be registered after web's own",
        )

    def test_error_dialog_says_it_plainly(self):
        """"Oops!" is not a voice AFENDA uses.

        Two halves, because neither alone can fail for the right reason. The
        bundle half proves the extension ships and names the right parent --
        upstream's own template, carrying "Oops!", is registered too and stays
        in the bundle either way, so asserting its absence would only ever be
        red. The lxml half proves the xpath still selects something in the
        current upstream template, which is what the browser does with the
        registered extension at runtime.
        """
        self.authenticate("admin", "admin")
        js = self._webclient_js(self.url_open("/app").text)
        registration = js.find('registerTemplateExtension("web.ErrorDialog"')
        self.assertGreater(registration, -1, "the AFENDA error-dialog extension is not in the bundle")
        block = js[registration:registration + 1200]
        self.assertIn("Something went wrong", block, "the extension does not carry the AFENDA title")
        self.assertNotIn(
            "Missing (extension) parent templates", js,
            "an OWL extension in this bundle names a template that does not exist",
        )
        # The xpath, against the template it inherits from.
        with file_open("web/static/src/core/errors/error_dialogs.xml", "rb") as f:
            upstream = lxml_etree.fromstring(f.read())
        with file_open("afenda_brand/static/src/xml/error_dialogs.xml", "rb") as f:
            ours = lxml_etree.fromstring(f.read())
        target = upstream.xpath("//t[@t-name='web.ErrorDialog']")
        self.assertEqual(len(target), 1, "web.ErrorDialog is no longer declared where we inherit from")
        patch = ours.xpath("//t[@t-inherit='web.ErrorDialog']/xpath")
        self.assertEqual(len(patch), 1, "the AFENDA extension no longer carries exactly one xpath")
        # The browser registers each template as its own document, so a leading
        # `//` in the expr is scoped to that template (template_inheritance.js:145
        # evaluates against the template element's ownerDocument). Re-parse to
        # reproduce that scope instead of searching the whole upstream file.
        scoped = lxml_etree.fromstring(lxml_etree.tostring(target[0]))
        nodes = scoped.xpath(patch[0].get("expr"))
        self.assertEqual(
            len(nodes), 1,
            f"{patch[0].get('expr')!r} selects {len(nodes)} nodes in web.ErrorDialog, not 1",
        )
        attribute = patch[0].find("attribute")
        self.assertIsNotNone(nodes[0].get(attribute.get("name")),
                             f"web.ErrorDialog has no {attribute.get('name')!r} attribute to replace")
        self.assertEqual(attribute.text, "Something went wrong")

    def _webclient_js(self, html):
        srcs = re.findall(r'src="(/web/assets/[^"]+web\.assets_web[^"]*\.js)"', html)
        self.assertTrue(srcs, "web.assets_web script not linked from /app")
        return self.url_open(srcs[0]).text

    def test_backend_theme_uses_brand_colors_and_fonts(self):
        self.authenticate("admin", "admin")
        html = self.url_open("/app").text
        hrefs = re.findall(r'href="(/web/assets/[^"]+web\.assets_web[^"]*\.css)"', html)
        self.assertTrue(hrefs, "web.assets_web stylesheet not linked from /app")
        css = self.url_open(hrefs[0]).text.lower()
        self.assertIn(BRAND["primary"].lower(), css)
        self.assertIn("source sans 3", css)
        self.assertIn("/afenda_brand/static/fonts/sourcesans3-vf.ttf", css)
        # o-add-unicode-support-font still appends the non-Latin fallback family.
        self.assertIn("unicode support noto", css)
        self.assertNotIn("#714b67", css, "Odoo enterprise purple must not survive")
        # Semantic tokens reach the compiled sheet...
        for name, color in (
            ("verified", BRAND["verified"]),
            ("ember", BRAND["ember"]),
            ("flag", BRAND["flag"]),
            ("ink", BRAND["ink"]),
            ("hairline", BRAND["hairline"]),
        ):
            self.assertIn(color.lower(), css, f"AFENDA {name} {color} is missing from the theme")
        for color in [BRAND["favorite"], *BRAND["tags"]]:
            self.assertIn(color.lower(), css, f"AFENDA palette color {color} is missing from the theme")
        # ...and Odoo's own semantic palette does not. Bootstrap's generic named
        # colors keep their own hexes whatever the theme -- $green comes from
        # web/static/src/scss/bootstrap_overridden.scss "Restore BS4 Colors" and
        # $red from web/static/src/scss/pre_variables.scss:39 -- so exactly one
        # declaration each may still hold the old hex, and nothing else may.
        bootstrap_named = {"#28a745": "--green: #28a745", "#dc3545": "--red: #dc3545"}
        for odoo_color in ("#28a745", "#ffac00", "#dc3545", "#f3cc00", "#d2317b", "#f0cda8"):
            declaration = bootstrap_named.get(odoo_color)
            if declaration:
                self.assertEqual(css.count(declaration), 1, f"{declaration!r} is not the lone survivor")
            rest = css.replace(declaration, "", 1) if declaration else css
            self.assertNotIn(odoo_color, rest, f"Odoo theme color {odoo_color} must not survive")
        # html_editor hardcodes the community purple in its table picker; our
        # override must come later in the bundle so it wins.
        purple = css.rfind("#71639e")
        override = css.find(".o-we-tablepicker .o-we-cell.active{background-color: #1e3a8a")
        self.assertGreater(override, purple, "table picker override must follow the hardcoded purple")
        for match in re.finditer(r"([^{}]+)\{[^{}]*#71639e", css):
            self.assertIn(".o-we-tablepicker", match.group(1), f"unexpected Odoo purple in rule {match.group(1)!r}")

    def test_dark_scheme_overrides_the_tokens(self):
        bundle = self.env["ir.qweb"]._get_asset_bundle("web.assets_web_dark", css=True, js=False)
        css = bundle.css().raw.decode().lower()
        # "primary" and "link" are the two values the light sheet never contains,
        # so they are what proves primary_variables.dark.scss was loaded at all.
        for name, color in BRAND["dark"].items():
            self.assertIn(color.lower(), css, f"dark {name} {color} is missing from the dark theme")

    # --- Email layouts -------------------------------------------------
    # Email clients drop <style>, so these templates are all inline values.
    # Nothing but mail's own markup can emit them, which is what makes the
    # "absent" assertions below able to fail.

    def _email_context(self, **overrides):
        """The context mail.mail_notification_layout reads, spelled out.

        Mirrors what `mail.render.mixin._render_encapsulate` assembles
        (addons/mail/models/mail_render_mixin.py:177-224); spelled out here so
        the render is not at the mercy of a helper's defaults.
        """
        values = {
            "message": self.env["mail.message"].sudo().new({"body": Markup("<p>body</p>")}),
            "company": self.env.ref("base.main_company"),
            "button_access": {"url": "/x", "title": "View"},
            "has_button_access": True,
            "email_notification_force_header": True,
            "email_notification_force_footer": True,
            "email_notification_allow_header": True,
            "email_notification_allow_footer": True,
            "subtype": self.env["mail.message.subtype"].sudo(),
            "subtitles": ["Record"],
            "is_discussion": False,
            "record_name": "Record",
            "tracking_values": [],
            "author_user": False,
            "email_add_signature": False,
            "signature": "",
            "show_unfollow": False,
            "lang": "en_US",
            "is_html_empty": is_html_empty,
        }
        values.update(overrides)
        return values

    def _render_email_layout(self, xmlid, **overrides):
        return self.env["ir.qweb"]._render(
            xmlid, self._email_context(**overrides), minimal_qcontext=True
        )

    def test_email_cta_contrast(self):
        """Regression for the upstream naming trap: mail's "primary" colour is
        the button TEXT and "secondary" is the button FILL. Swap the two
        company fields back and this button is Ledger Blue on Ledger Blue."""
        html = self._render_email_layout("mail.mail_notification_layout")
        tree = lxml_html.fromstring(html)
        # Anchored on structure, not on a style substring: the CTA cell is the
        # td whose direct child is the button_access link.
        cells = tree.xpath("//td[a[@href='/x']]")
        self.assertEqual(len(cells), 1, "the CTA cell was not rendered")
        fill = re.search(r"background:\s*(#[0-9A-Fa-f]{6})", cells[0].get("style") or "")
        self.assertTrue(fill, "the CTA cell has no background colour")
        anchors = cells[0].xpath("./a")
        self.assertEqual(len(anchors), 1, "the CTA cell has no link")
        text = re.search(r"color:\s*(#[0-9A-Fa-f]{6})", anchors[0].get("style") or "")
        self.assertTrue(text, "the CTA link has no colour")
        self.assertEqual(fill.group(1).upper(), BRAND["primary"])
        self.assertEqual(text.group(1).upper(), BRAND["on_primary"])

    def test_email_default_layout_is_branded(self):
        """Regression: without the //body xpath the notification email is
        Verdana on Odoo's #454748, and the footer links out instead of showing
        the AFENDA mark."""
        html = self._render_email_layout("mail.mail_notification_layout")
        body = lxml_html.fromstring(html).xpath("//body")[0].get("style")
        self.assertIn("Source Sans 3", body)
        self.assertNotIn("Verdana", body)
        self.assertIn(BRAND["ink"], body)
        self.assertIn("/afenda_brand/static/img/logo_email_2x.png", html)
        self.assertNotIn("utm_source=db", html, "the outbound 'Powered by' link survived")
        for tell in ("Verdana", "#454748", "#875A7B"):
            self.assertNotIn(tell, html, f"default mail layout still carries {tell!r}")

    def test_email_light_layout_is_branded(self):
        """Regression: without the three light-layout xpaths the card sits on
        Odoo grey #F1F1F1, has no edge, and the footer cell has no rule."""
        html = self._render_email_layout("mail.mail_notification_light")
        tree = lxml_html.fromstring(html)
        frame = tree.xpath("//table[contains(@style, 'background-color')]")[0].get("style")
        self.assertIn(BRAND["paper"], frame, "the email frame is not AFENDA paper")
        card = tree.xpath("//table[@width='590']")[0].get("style")
        self.assertIn(f"border:1px solid {BRAND['hairline']}", card, "the email card has no edge")
        # The card and footer styles are appended to upstream's, so upstream's
        # own `color` is still in the string; what matters is which one an
        # email client reads last.
        self.assertEqual(self._last_color(card), BRAND["ink"], "the card text is not ink")
        footer = tree.xpath("//td[contains(@style, 'font-size:11px')]")[0].get("style")
        self.assertIn(f"border-top:1px solid {BRAND['hairline']}", footer)
        self.assertEqual(self._last_color(footer), BRAND["graphite"])
        self.assertIn("/afenda_brand/static/img/logo_email_2x.png", html)
        for tell in ("Verdana", "#F1F1F1", "utm_source=db"):
            self.assertNotIn(tell, html, f"light mail layout still carries {tell!r}")

    def test_email_mark_is_sized_for_outlook(self):
        """Regression: Outlook's Word engine ignores CSS sizing and lays an
        image out at its native width, so a 1200px asset with only height="16"
        blows the 590px card apart. Both layouts must ship the attribute pair
        and point at the pre-scaled mark."""
        with file_open("afenda_brand/static/img/logo_email_2x.png", "rb") as f:
            raw = f.read()
        self.assertEqual(Image.open(io.BytesIO(raw)).size, (128, 32), "the mark is not the 2x asset")
        self.assertLess(len(raw), 12_000, "the mark is too heavy to ship on every notification")
        # Transparent corner: this row sits on the paper frame in the light
        # layout, so a white-matted asset would draw a box on off-white.
        self.assertEqual(Image.open(io.BytesIO(raw)).convert("RGBA").getpixel((0, 0))[3], 0)
        for xmlid in ("mail.mail_notification_layout", "mail.mail_notification_light"):
            tree = lxml_html.fromstring(self._render_email_layout(xmlid))
            marks = tree.xpath("//img[contains(@src, 'logo_email')]")
            self.assertEqual(len(marks), 1, f"{xmlid} does not carry the AFENDA mark")
            mark = marks[0]
            self.assertEqual(mark.get("width"), "64", f"{xmlid}: no width attribute for Outlook")
            self.assertEqual(mark.get("height"), "16", f"{xmlid}: no height attribute")
            self.assertIn("max-width:64px", (mark.get("style") or "").replace(" ", ""))
            self.assertIn("logo_email_2x.png", mark.get("src"))

    @staticmethod
    def _last_color(style):
        """The `color` an email client ends up reading out of one inline style."""
        values = re.findall(r"(?:^|;)\s*color\s*:\s*([^;]+)", style)
        return values[-1].strip().upper() if values else None
