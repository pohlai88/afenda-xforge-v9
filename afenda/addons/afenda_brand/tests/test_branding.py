import ast
import base64
import collections
import hashlib
import inspect
import io
import itertools
import pathlib
import re
from unittest import mock

from lxml import etree as lxml_etree
from lxml import html as lxml_html
from markupsafe import Markup
from PIL import Image

from odoo.modules.module import load_script
from odoo.tests import HttpCase, tagged
from odoo.tools import file_open, is_html_empty

# The generator that drew the icons this module ships, reached from the repo
# root the server is started in. Only the blend is borrowed: the palette these
# tests hold the icons to still comes from BRAND, so a generator drawing in the
# wrong colours would fail here rather than agree with itself.
from afenda.tools.app_icons import controlled_overlap_colour

from .. import hooks
from ..brand import BRAND
from ..hooks import (
    _UPSTREAM_REPORT_FONT,
    _apply_company_branding,
    refresh_cached_brand_images,
)

ODOO_TELLS = ("odoo.com", "Powered by Odoo", "odoo_logo", "Odoo S.A.")


def _rgb(colour: str) -> tuple[int, int, int]:
    """``"#1E3A8A"`` -> ``(30, 58, 138)``."""
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


def _png_b64(rgb):
    """A tiny PNG, base64 as a Binary field stores it.

    Stands in for artwork this addon shipped in an earlier release: the real
    bytes are only in git history, so the tests that need "some blob whose hash
    we control" make their own and patch the hash table.
    """
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), rgb).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue())


def _on_disk(path):
    with file_open(f"afenda_brand/static/{path}", "rb") as f:
        return base64.b64encode(f.read())


# A 1x1 PNG, base64 as a Binary field stores it: stands in for a favicon an
# administrator uploaded, and is nothing the addon would ever write itself.
_CUSTOM_FAVICON = (
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    b"hQGAhKmMIQAAAABJRU5ErkJggg=="
)


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
            "favicon": _CUSTOM_FAVICON,
        })

        # The default call, which is what `post_init_hook` makes: the
        # superseded repair is opt-in, so the stale email colours survive it.
        # Regression: make the repair unconditional and every path that brands
        # companies -- the install hook, any future caller -- starts carrying
        # the risk of overwriting an administrator who genuinely picked ink for
        # the notification button.
        _apply_company_branding(self.env)
        self.assertEqual(stale.email_secondary_color.upper(), BRAND["ink"])
        self.assertEqual(stale.email_primary_color.upper(), BRAND["primary"])
        # The fields guarded on upstream's own default are repaired either way.
        self.assertEqual(stale.font, "Source_Sans_3")

        # What the migration calls.
        _apply_company_branding(self.env, replace_superseded=True)

        # Regression: guard the two email colours on the upstream default alone
        # and #0F172A is not it, so the company is skipped forever -- every
        # upgrade re-ships the unreadable Ledger-Blue-on-ink CTA button that
        # the inversion fix was supposed to end.
        self.assertEqual(stale.email_secondary_color.upper(), BRAND["primary"])
        self.assertEqual(stale.email_primary_color.upper(), BRAND["on_primary"])
        # Regression: leave the branding body inside post_init_hook and the
        # document defaults never reach a company that already exists. (That
        # the migration script itself is present and loadable is
        # `test_migration_script_is_wired_to_the_manifest_version`; this test
        # calls the function directly and cannot see the script at all.)
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
        # The favicon has no "still upstream's" test available (web_favicon's
        # default carries a random colour bar), so it is written by
        # `post_init_hook` alone. Regression: move those two lines back into
        # `_apply_company_branding` and every upgrade overwrites an uploaded
        # company favicon with the AFENDA one.
        self.assertEqual(chosen.favicon, _CUSTOM_FAVICON)

    def test_migration_script_is_wired_to_the_manifest_version(self):
        """The migration script is the subject of this change and the test
        above cannot see it: that one calls `_apply_company_branding` directly
        and stays green with the script deleted.

        Regressions: delete `migrations/<version>/post-migrate.py`; bump the
        manifest version without adding the matching directory (Odoo looks the
        directory up by version, odoo/modules/migration.py:186-215, and simply
        finds nothing); or give `migrate` a signature Odoo rejects --
        `exec_script` requires exactly `(cr, version)` and raises TypeError
        otherwise (odoo/modules/migration.py:245-252), which aborts the whole
        upgrade.
        """
        addon = pathlib.Path(__file__).resolve().parent.parent
        version = ast.literal_eval((addon / "__manifest__.py").read_text(encoding="utf-8"))["version"]
        script = addon / "migrations" / version / "post-migrate.py"
        self.assertTrue(
            script.is_file(),
            f"manifest version {version} has no migrations/{version}/post-migrate.py",
        )
        module = load_script(str(script), "afenda_brand_post_migrate_under_test")
        self.assertEqual(
            tuple(inspect.signature(module.migrate).parameters), ("cr", "version"),
            "Odoo only accepts a migrate(cr, version) signature",
        )

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
        (odoo/addons/base/models/ir_ui_menu.py:158-162). Rendering new icons on
        disk does not touch it, so without the refresh step in post_init_hook an
        existing database keeps Odoo's teal hexagons for every root menu.

        The icons are free-standing duotone marks - a glyph in one brand colour,
        an accent shape in a second, and a controlled darkening of the two where
        they cross - so there is no tile edge to probe. What is checked instead
        is that every colour with real coverage comes from the brand palette,
        which is exactly what an unrefreshed Odoo hexagon fails.
        """
        roots = self.env["ir.ui.menu"].sudo().with_context(active_test=False).search(
            [("parent_id", "=", False), ("web_icon", "!=", False)]
        )
        self.assertTrue(roots, "no root menu carries a web_icon")
        palette = [_rgb(h) for h in [BRAND["primary"]] + BRAND["tags"]]
        # A colour is legitimate if it is a brand colour or the crossing of two
        # of them. The crossing is not a plain multiply: raw multiply sends most
        # brand pairs to a near-black that reads as a hole, so the generator
        # eases it back toward the midpoint until it clears a luminance floor.
        allowed = set(palette) | {
            controlled_overlap_colour(a, b) for a, b in itertools.product(palette, repeat=2)
        }
        checked = 0
        for menu in roots:
            # A three-part web_icon is a "built" icon (class,colour,background)
            # and stores no image at all; only the two-part `module,path` form
            # has web_icon_data.
            if len(menu.web_icon.split(",")) != 2 or not menu.web_icon_data:
                continue
            image = Image.open(io.BytesIO(base64.b64decode(menu.web_icon_data))).convert("RGBA")
            pixels = list(image.getdata())
            clear = sum(1 for p in pixels if p[3] == 0) / len(pixels)
            self.assertGreater(clear, 0.20, f"{menu.name}: {menu.web_icon} is a filled tile, not a mark")
            # 3% of the canvas: below that a colour is the antialiased seam
            # between two shapes, not one of the colours the icon is drawn in.
            counts = collections.Counter(p[:3] for p in pixels if p[3] == 255)
            for colour, n in counts.items():
                if n < 0.03 * len(pixels):
                    continue
                self.assertIn(
                    colour, allowed,
                    f"{menu.name}: {menu.web_icon} is drawn in {colour}, which is not an AFENDA colour",
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
        # Odoo purple and #1AD3BB the Odoo teal the upstream icon.svg files were
        # drawn in. Discuss is a communication app: indigo glyph, mulberry
        # accent, and their crossing where the accent cuts the bubble.
        svg = self.url_open("/mail/static/description/icon.svg").text
        for dead in ("#985184", "#1AD3BB"):
            self.assertNotIn(dead, svg, "the mail app icon is still Odoo artwork")
        indigo, mulberry = "#3448A8", "#A8447A"
        self.assertLessEqual({indigo, mulberry}, set(BRAND["tags"]), "the tag palette moved under the icons")
        overlap = "#%02X%02X%02X" % controlled_overlap_colour(_rgb(indigo), _rgb(mulberry))
        for colour in (indigo, mulberry, overlap):
            self.assertIn(colour, svg, f"the mail app icon is missing {colour}")
        # Every root menu this database installs happens to carry a small corner
        # accent, so none of their crossings reaches the 3% floor above and the
        # loop never actually probes an overlap colour. Discuss does: its disc
        # cuts a third of the bubble. Probing the file the apps menu serves
        # keeps the colour model under test instead of merely under discussion.
        served = Image.open(io.BytesIO(
            self.url_open("/mail/static/description/icon.png").content)).convert("RGBA")
        counts = collections.Counter(p[:3] for p in served.getdata() if p[3] == 255)
        self.assertGreater(counts[_rgb(overlap)], 0.03 * served.width * served.height,
                           f"the mail icon is not drawn with its crossing colour {overlap}")
        for colour, n in counts.items():
            if n >= 0.03 * served.width * served.height:
                self.assertIn(colour, allowed,
                              f"the mail app icon is drawn in {colour}, which is not an AFENDA colour")

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

    def test_migration_replaces_the_logo_the_latch_hides(self):
        """A logo AFENDA shipped earlier is replaceable; an upload is not.

        `_apply_company_branding` writes the logo only while
        `uses_default_logo` is true, and that field is a stored compute
        comparing the stored logo against img/logo.png as it stands *now*
        (odoo/addons/base/models/res_company.py:175-178). The moment it
        recomputes after the mark is redrawn, our own previous artwork stops
        matching, the flag latches false, and the logo is frozen as though an
        administrator had chosen it -- so `-u` can never fix it again.

        Regression this catches: drop the `_SUPERSEDED_LOGO_SHA256` arm of that
        guard and every database installed before the redraw keeps the old mark
        on its invoices for good, silently, with the suite still green.
        """
        superseded = _png_b64((1, 2, 3))
        digest = hashlib.sha256(base64.b64decode(superseded)).hexdigest()
        stale = self.env["res.company"].create({"name": "Stale logo", "logo": superseded})
        # The premise: writing a logo that is not the current file recomputes the
        # flag to false. If this ever fails the latch is gone and so is the bug.
        self.assertFalse(stale.uses_default_logo, "the latch this test is about did not engage")

        # The install hook's call must not touch it: without the hash table it
        # cannot tell our artwork from an administrator's, so it leaves it.
        _apply_company_branding(self.env)
        self.assertEqual(bytes(stale.logo), bytes(superseded),
                         "the default call must stay conservative about logos")

        # What the migration calls. Only now is the superseded artwork known.
        with mock.patch.object(hooks, "_SUPERSEDED_LOGO_SHA256", (digest,)):
            _apply_company_branding(self.env, replace_superseded=True)
        self.assertEqual(bytes(stale.logo), bytes(_on_disk("img/logo.png")),
                         "the migration did not refresh a superseded logo")

        # The other half: an upload we have never shipped is never ours to take.
        chosen = self.env["res.company"].create({"name": "Chosen logo", "logo": _png_b64((9, 8, 7))})
        before = bytes(chosen.logo)
        with mock.patch.object(hooks, "_SUPERSEDED_LOGO_SHA256", (digest,)):
            _apply_company_branding(self.env, replace_superseded=True)
        self.assertEqual(bytes(chosen.logo), before, "an administrator's logo was overwritten")

    def test_refresh_cached_brand_images_is_guarded(self):
        """The bot avatar and the PWA icon are copies of icon-512.png, not
        references, so a redraw leaves them stale -- but only AFENDA's own
        superseded copy may be replaced.

        Regression: write them unconditionally and every upgrade stomps an
        administrator's uploaded PWA icon and bot avatar.
        """
        ours = _png_b64((4, 5, 6))
        digest = hashlib.sha256(base64.b64decode(ours)).hexdigest()
        bot = self.env.ref("base.partner_root").sudo()

        bot.image_1920 = ours
        with mock.patch.object(hooks, "_SUPERSEDED_ICON_SHA256", (digest,)):
            written = refresh_cached_brand_images(self.env)
        self.assertIn("partner_root.image_1920", written)
        # image_1920 goes through the image pipeline, so compare what it depicts
        # rather than the bytes: the 2x2 stand-in must be gone.
        with Image.open(io.BytesIO(base64.b64decode(bot.image_1920))) as refreshed:
            self.assertEqual(refreshed.size, (512, 512), "the bot avatar is not the 512px mark")

        # An avatar we have never shipped is left exactly as it is.
        foreign = _png_b64((7, 7, 7))
        bot.image_1920 = foreign
        with mock.patch.object(hooks, "_SUPERSEDED_ICON_SHA256", (digest,)):
            written = refresh_cached_brand_images(self.env)
        self.assertNotIn("partner_root.image_1920", written)
        with Image.open(io.BytesIO(base64.b64decode(bot.image_1920))) as kept:
            self.assertEqual(kept.size, (2, 2), "an administrator's bot avatar was overwritten")

        # The PWA icon lands as a web_pwa_customize attachment, and having landed
        # is no longer superseded, so a second pass leaves it alone.
        settings = self.env["res.config.settings"].sudo()
        stored = self.env["ir.attachment"].sudo().search(
            [("url", "=like", settings._pwa_icon_url_base + ".%")], limit=1
        )
        self.assertTrue(stored, "no PWA icon attachment was written")
        with mock.patch.object(hooks, "_SUPERSEDED_ICON_SHA256", (digest,)):
            self.assertNotIn("pwa_icon", refresh_cached_brand_images(self.env),
                             "the refresh is not idempotent: it rewrites a current icon")

    def test_every_migration_is_loadable_not_only_the_current_one(self):
        """`test_migration_script_is_wired_to_the_manifest_version` only checks the
        version the manifest points at, so an older script can rot unnoticed --
        and it did:
        19.0.1.0.3 stopped being the manifest version the moment 19.0.1.0.4
        landed, and nothing was checking it any more.

        Every script here still runs on a real upgrade: Odoo loads each version
        directory above the installed version and up to the manifest's, in order,
        so a database on .1 executes all of them. A script that no longer imports
        or has drifted from `migrate(cr, version)` breaks that upgrade, not this
        release.
        """
        addon = pathlib.Path(__file__).resolve().parent.parent
        scripts = sorted((addon / "migrations").glob("*/post-migrate.py"))
        self.assertTrue(scripts, "the migrations directory has gone missing")
        for script in scripts:
            version = script.parent.name
            module = load_script(str(script), f"afenda_brand_{version.replace('.', '_')}")
            self.assertEqual(
                tuple(inspect.signature(module.migrate).parameters), ("cr", "version"),
                f"{version}: Odoo only accepts a migrate(cr, version) signature",
            )

    def test_every_test_class_would_actually_be_collected(self):
        """A test class that does not descend from Odoo's `BaseCase` is silently
        dropped, and this repo's log level hides the reason.

        `TagsSelector` excludes anything without a `test_tags` attribute
        (odoo/tests/tag_selector.py:88-90), and `test_tags` is assigned by
        `BaseCase.__init_subclass__` (odoo/tests/common.py:309-318). So a plain
        `unittest.TestCase` in an addon's tests/ is discovered, then filtered out
        before it runs -- and the skip is logged at DEBUG, which
        `afenda/odoo.conf`'s `log_level = warn` swallows. The suite reports green
        over tests that never executed.

        Found by the session building afenda_api_docs: nine of its twelve tests
        were invisible this way and the run said "0 failed of 3 tests". Nothing in
        Odoo enforces or documents the convention, precisely because everything
        already follows it.

        Static on purpose -- it reads the source of every AFENDA addon rather than
        importing it, so a module that is not installed in this database is still
        covered. It lives here because afenda_brand is the addon every other one
        depends on, and because a guard that only watched its own tests would have
        missed the case that prompted it.
        """
        # Odoo's own case classes, all of which reach BaseCase.
        odoo_cases = {
            "BaseCase", "TransactionCase", "SingleTransactionCase", "SavepointCase",
            "HttpCase", "HttpCaseWithUserDemo", "HttpCaseWithUserPortal",
            "MailCommon", "TestMailCommon", "AccountTestInvoicingCommon",
            "TransactionCaseWithUserDemo", "TransactionCaseWithUserPortal",
        }
        addons = pathlib.Path(__file__).resolve().parents[2]
        offenders = []
        for source in sorted(addons.glob("*/tests/*.py")):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}

            def bases(node, seen=()):
                """Every base name reachable from `node`, following same-file parents."""
                for base in node.bases:
                    name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", None)
                    if not name or name in seen:
                        continue
                    yield name
                    if name in classes:
                        yield from bases(classes[name], seen + (name,))

            for name, node in classes.items():
                methods = [n.name for n in node.body
                           if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
                if not methods:
                    continue  # a helper or a mixin, never collected on its own
                reachable = set(bases(node))
                if not reachable & odoo_cases:
                    offenders.append(
                        f"{source.relative_to(addons).as_posix()}::{name} "
                        f"({len(methods)} tests) inherits {sorted(reachable) or ['object']}"
                    )
        self.assertFalse(
            offenders,
            "these classes would be silently skipped by TagsSelector, not run:\n  "
            + "\n  ".join(offenders),
        )
