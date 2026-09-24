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


# Manifest versions bumped with no migration work to do.
#
# A bump is not only a carrier for a script. deploy/init.sh upgrades with
# `module upgrade --outdated`, which selects modules by comparing manifest
# version to installed version, so a view or asset change reaches a deployed
# database ONLY if the version moves -- there is no manual `-u` in the deploy
# path. Listing a version here is the deliberate statement that the upgrade
# needs nothing beyond the reload Odoo already does.
#
# Forgetting a script you DID need still fails: you have to come here and say
# so, in writing, next to the reason.
_VERSIONS_WITHOUT_MIGRATION = {
    "19.0.1.0.6": "auth surface, shell theming, mail header -- views and SCSS "
                  "reload on upgrade; no record needs rewriting",
}


@tagged("post_install", "-at_install")
class TestBranding(HttpCase):
    """What a normal user sees must say AFENDA, never Odoo."""

    def test_login_page_is_branded(self):
        html = self.url_open("/web/login").text
        self.assertIn("<title>AFENDA xForge</title>", html.replace("\n", ""))
        # Not the AFENDA file specifically: a configured tenant's own favicon
        # is served here instead, which is the point of the third fallback.
        self.assertRegex(html, r'rel="shortcut icon"[^>]*href="[^"]+"',
                         "the login page links no favicon")
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

    def _frontend_css(self, url="/web/login"):
        html = self.url_open(url).text
        hrefs = re.findall(r'href="(/web/assets/[^"]+web\.assets_frontend[^"]*\.css)"', html)
        self.assertTrue(hrefs, f"web.assets_frontend stylesheet not linked from {url}")
        return html, self.url_open(hrefs[0]).text.lower()

    def test_auth_band_is_the_masthead_at_every_width(self):
        """The band sits above the form and is never taken away.

        This replaces a test that pinned the opposite shape - a two-part canvas
        that opened at the lg breakpoint and collapsed below it. The owner's
        composition has one form at every width, so the invariant inverts: the
        band has to be the FIRST thing in the page's stack, its rules have to
        be unconditional, and no second rule may exist to collapse it. "Exactly
        one rule" is the load-bearing half - a `display: none` for the band
        inside some media query is the obvious way to break "at every width",
        and it would leave the unconditional rule looking perfectly correct.
        """
        html, css = self._frontend_css()
        doc = lxml_html.fromstring(html)

        stack = doc.find_class("o_afenda_auth")
        self.assertEqual(len(stack), 1, "the auth stack is not rendered exactly once")
        blocks = [child.get("class") for child in stack[0] if isinstance(child.tag, str)]
        self.assertEqual(
            blocks, ["o_afenda_auth_panel", "o_afenda_auth_form"],
            "the band is not the first block above the form",
        )

        lockup = "/afenda_brand/static/img/logo_dark.svg"
        self.assertIn(lockup, html, "the band carries no lockup")
        self.assertEqual(self.url_open(lockup).status_code, 200, f"{lockup} is not served")

        band = list(re.finditer(r"\.o_afenda_login\s+\.o_afenda_auth_panel\s*\{([^}]*)\}", css))
        self.assertTrue(band, "the band has no rule in the frontend bundle")
        self.assertEqual(len(band), 1,
                         "a second rule redraws the band: one of them is width-dependent")
        self.assertIn(BRAND["ink"].lower(), band[0].group(1), "the band is not ink")
        self.assertRegex(band[0].group(1), r"display:\s*flex", "the band does not lay out")
        self._assert_not_media_gated(
            css, band[0].start(), "the band is drawn only inside a media query")

        # The grid that made the old canvas two columns is gone, not merely
        # overridden: a leftover `grid-template-columns` would put the band
        # beside the form again the moment something restored `display: grid`.
        stacked = list(re.finditer(r"\.o_afenda_login\s+\.o_afenda_auth\s*\{([^}]*)\}", css))
        self.assertEqual(len(stacked), 1, "the auth stack is not drawn by exactly one rule")
        self.assertNotIn("grid", stacked[0].group(1), "the two-column grid is still here")
        self._assert_not_media_gated(
            css, stacked[0].start(), "the page stacks only inside a media query")

    def test_the_band_carries_both_marks_and_the_card_carries_none(self):
        """Two marks in the band, two different names, and no mark in the card.

        The tenant owns the instance and we only made it, so the band states a
        relationship rather than an adjacency: the tenant's own logo is seated
        on a paper plate at the head of the band and ours is the smaller mark
        at the tail. The plate's ground is the part worth pinning. Anything
        `res_company.logo_web` holds is customer artwork drawn for a white page
        - that is where Odoo renders this same image everywhere else - so it
        gets paper under it. Paint the plate ink and a real customer's dark
        logo disappears on a surface we would never see it fail on, because
        this database's own company logo happens to be light.

        The card half is a DOM property, not a stylesheet one: the head block
        is deleted by the inheritance, so there is no width, no bundle rebuild
        and no stylesheet failure that can put a mark back inside the card.
        """
        html, css = self._frontend_css()
        doc = lxml_html.fromstring(html)
        band = doc.find_class("o_afenda_auth_panel")
        self.assertEqual(len(band), 1, "the band is not rendered exactly once")

        lockups = doc.find_class("o_afenda_auth_lockup")
        self.assertEqual(len(lockups), 1, "the product lockup is not rendered exactly once")
        lockup = lockups[0]
        self.assertEqual(lockup.get("src"), "/afenda_brand/static/img/logo_dark.svg")
        self.assertIn(BRAND["product"], lockup.get("alt") or "",
                      "the product lockup has no accessible name")
        # An LCP image must not be deferred.
        self.assertIsNone(lockup.get("loading"), "the product lockup is lazy-loaded")
        served = self.url_open(lockup.get("src"))
        self.assertEqual(served.status_code, 200, "the vector lockup is not served")
        self.assertIn(b"<svg", served.content[:256], "the lockup is not a vector")

        # Upstream's own <img>, moved rather than copied: one element, so one
        # "Logo" in the accessibility tree, and its src stays upstream's.
        tenants = doc.xpath("//img[contains(@src, 'company_logo')]")
        self.assertEqual(len(tenants), 1, "the tenant logo is not rendered exactly once")
        tenant = tenants[0]
        self.assertTrue((tenant.get("alt") or "").strip(),
                        "the tenant logo has no accessible name")
        self.assertNotEqual(
            (tenant.get("alt") or "").strip(), (lockup.get("alt") or "").strip(),
            "both marks announce the same name",
        )
        self.assertFalse(tenant.get("style"),
                         "an inline size still outranks the cap in login.scss")

        for mark, what in ((lockup, "product lockup"), (tenant, "tenant logo")):
            self.assertIn(band[0], list(mark.iterancestors()), f"the {what} is not in the band")

        # Nothing brand-like inside the card, at any width: no head element
        # survives the inheritance and the card holds no image at all.
        self.assertFalse(doc.find_class("o_afenda_card_head"),
                         "the card head block is still in the page")
        cards = doc.find_class("o_database_list")
        self.assertEqual(len(cards), 1, "the login card was not rendered")
        self.assertFalse(cards[0].xpath(".//img"), "an image still renders inside the card")

        plate = re.search(r"\.o_afenda_login\s+\.o_afenda_auth_plate\s*\{([^}]*)\}", css)
        self.assertTrue(plate, "the tenant plate has no rule in the frontend bundle")
        self.assertIn(BRAND["paper"].lower(), plate.group(1),
                      "the tenant logo is seated on something other than paper")
        self._assert_not_media_gated(
            css, plate.start(), "the tenant plate exists only inside a media query")

        box = re.search(r"\.o_afenda_login\s+\.o_afenda_auth_lockup\s*\{([^}]*)\}", css)
        self.assertTrue(box, "the lockup has no rule in the frontend bundle")
        # The property name alone would pass on `aspect-ratio: auto`, which
        # reserves nothing; the point of the rule is the number.
        self.assertRegex(box.group(1), r"aspect-ratio:\s*2\.5",
                         "the lockup reserves no box of the lockup's own shape")

        cap = re.search(r"\.o_afenda_login\s+\.o_afenda_auth_tenant\s*\{([^}]*)\}", css)
        self.assertTrue(cap, "the tenant logo has no rule in the frontend bundle")
        # Bounded by HEIGHT, and the aspect ratio left free. logo_web is
        # image_process(logo, size=(180, 0)) (odoo/addons/base/models/
        # res_company.py:169-172): at most 180 wide, height whatever the
        # artwork is. A 45px height cap once rendered this tenant's 179x172
        # badge at 47x45 -- smaller than our own lockup, with its wordmark
        # illegible -- so the box, not the bound, was the bug.
        # Asserted as capping properties: `min-width: 180px` contains "180px"
        # too and would mean the opposite of a cap.
        for prop, bound in (("max-width", "180px"), ("max-height", "72px")):
            self.assertRegex(
                cap.group(1), rf"{prop}:\s*{re.escape(bound)}",
                f"the tenant logo is not bounded by {prop}",
            )
        # ...and nothing fixes a dimension, which would distort an aspect ratio
        # this rule cannot know.
        self.assertRegex(cap.group(1), r"width:\s*auto", "the tenant logo has a forced width")
        self.assertRegex(cap.group(1), r"height:\s*auto", "the tenant logo has a forced height")
        self._assert_not_media_gated(
            css, cap.start(), "the tenant logo is capped only inside a media query")

    def test_the_band_composes_without_the_tagline(self):
        """Every login_layout page but /web/login renders the band without a line.

        Only controllers/home.py:18 (the web_login override) puts
        `afenda_tagline` in the qcontext, so /web/reset_password and
        /web/signup get the mark block with nothing under the lockup. The old
        panel needed a rule for that case - a lockup alone in a tall column was
        pinned to the top of an empty ink field by space-between, and
        `:last-child { margin-top: auto }` seated it. A band needs no such
        compensation, so there is no CSS to assert here and none is invented:
        the block is a column of one, in the same place in the band either way.
        What is pinned instead is the page, which is the claim that matters.
        """
        if not self.env["ir.module.module"].search_count(
                [("name", "=", "auth_signup"), ("state", "=", "installed")]):
            self.skipTest("auth_signup is not installed: no login_layout page without a tagline")
        page = self.url_open("/web/reset_password")
        self.assertEqual(page.status_code, 200, "/web/reset_password is not served")
        doc = lxml_html.fromstring(page.text)
        self.assertEqual(len(doc.find_class("o_afenda_auth_panel")), 1,
                         "/web/reset_password renders no band")
        self.assertEqual(len(doc.find_class("o_afenda_auth_lockup")), 1,
                         "/web/reset_password renders no lockup")
        self.assertEqual(len(doc.find_class("o_afenda_auth_tenant")), 1,
                         "/web/reset_password renders no tenant logo")
        self.assertFalse(doc.find_class("o_afenda_auth_line"),
                         "the tagline reached a page whose controller never sets it")
        self.assertFalse(doc.find_class("o_afenda_card_head"),
                         "/web/reset_password still has a card head")

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
            # NOT asserted as "the bytes are AFENDA's". That was only ever true
            # of a database nobody had configured: a tenant with its own favicon
            # is the feature working, not failing -- the same mistake
            # test_company_defaults used to make about the company name. What is
            # pinned instead is the contract: whatever is served is a real image
            # of the type a tab can render, and when the company HAS a favicon,
            # that is what is served rather than AFENDA's.
            self.assertTrue(
                icon.headers.get("Content-Type", "").startswith("image/"),
                f"{url}: the favicon is not served as an image",
            )
            company = self.env.ref("base.main_company").sudo()
            if company.favicon:
                self.assertEqual(
                    icon.content, base64.b64decode(company.favicon),
                    f"{url} serves AFENDA's favicon while the tenant has its own",
                )

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
        """AFENDA is the SYSTEM; the main company is a TENANT.

        This used to assert the main company's own name and logo were AFENDA's,
        which is only true of a database nobody has configured yet. It is a
        defaults test, and a tenant that has set its own name and artwork is
        the hook working, not failing: `_apply_company_branding` renames only a
        company still carrying an Odoo default (hooks.py:184, against
        _DEFAULT_COMPANY_NAMES) and guards the logo on `uses_default_logo`.
        Asserting otherwise made a real tenant's configuration read as a
        regression -- which is exactly what happened here.

        So the defaults are asserted on a company this test creates and
        therefore controls. That the hook also reaches an ALREADY EXISTING
        company at install is a different contract, and it is covered by
        test_migration_reapplies_company_branding, which builds both companies
        it needs rather than borrowing whatever the live database has.
        """
        company = self.env.ref("base.main_company")
        with file_open("afenda_brand/static/img/logo.png", "rb") as f:
            expected_size = Image.open(io.BytesIO(f.read())).size
        self.assertTrue(company.favicon, "the main company has no favicon at all")
        new_company = self.env["res.company"].create({"name": "Second"})
        self.assertEqual(self._logo_size(new_company.logo), expected_size, "new companies get the AFENDA logo")
        # mail reads these from the email: "primary" is the CTA button text,
        # "secondary" is the button fill. A blue-on-blue button is unreadable.
        # Asserted on the company this test created, for the reason in the
        # docstring: these are tenant-editable too (Settings > Companies), so
        # reading them off the live main company would be the same mistake.
        self.assertEqual(new_company.email_secondary_color.upper(), BRAND["primary"])
        self.assertEqual(new_company.email_primary_color.upper(), "#FFFFFF")
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
        if version in _VERSIONS_WITHOUT_MIGRATION:
            self.assertFalse(
                script.is_file(),
                f"{version} is declared as needing no migration but ships one; "
                f"remove it from _VERSIONS_WITHOUT_MIGRATION",
            )
        else:
            self.assertTrue(
                script.is_file(),
                f"manifest version {version} has no migrations/{version}/post-migrate.py "
                f"and is not declared in _VERSIONS_WITHOUT_MIGRATION",
            )
        # Every script the module ships, not only the current version's: a
        # signature Odoo rejects aborts the whole upgrade, and an old directory
        # still runs on a database far enough behind.
        scripts = sorted((addon / "migrations").glob("*/post-migrate.py"))
        self.assertTrue(scripts, "the module ships no migration scripts at all")
        for path in scripts:
            module = load_script(str(path), f"afenda_brand_post_migrate_{path.parent.name}")
            self.assertEqual(
                tuple(inspect.signature(module.migrate).parameters), ("cr", "version"),
                f"{path.parent.name}: Odoo only accepts a migrate(cr, version) signature",
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
        # The scalar tokens only: BRAND["dark"]["ramp"] is pinned through its
        # consumers in test_neutral_ramp_reaches_both_schemes, because a bare
        # substring for a ramp step is satisfied by colors this scheme sets
        # elsewhere and would not fail if the step went missing.
        for name, color in BRAND["dark"].items():
            if not isinstance(color, str):
                continue
            self.assertIn(color.lower(), css, f"dark {name} {color} is missing from the dark theme")

    def test_dark_scheme_survives_the_inverted_ramp(self):
        """The $o-gray-* consumers the inversion alone gets wrong.

        Each is upstream reading the ramp through a Bootstrap-layer variable
        whose sense only survives walking light-to-dark, so
        primary_variables.dark.scss restates the variable. Both bundles are
        pinned: the light half is what proves the restatement is scoped to the
        dark bundle and did not move the light scheme.

        Not asserted, because it is knowingly unfixed: the pager indicator
        reads $o-gray-200 directly for border and background
        (web/static/src/core/pager/pager_indicator.scss:8-10), so in this
        scheme it is the view color on the view. No token reaches it and this
        module adds no dark-bundle selectors; the gap is written up in
        primary_variables.dark.scss beside the fixes that were reachable.
        """
        light = self._bundle_css("web.assets_web")
        dark = self._bundle_css("web.assets_web_dark")

        # Tooltips: caption $o-gray-200 (bootstrap_overridden.scss:236) on a
        # ground of $o-black (:29). Neither scheme lifts $o-black, which is why
        # --emphasis-color is asserted too -- it is what makes "the caption must
        # be the light end of the ramp" a requirement rather than a preference.
        self.assertIn("--emphasis-color: #000000;", dark, "the dark tooltip ground is no longer black")
        for css, scheme in ((light, "light"), (dark, "dark")):
            self.assertIn("--tooltip-color: #f3f4f6;", css,
                          f"the {scheme} tooltip caption is not readable on a black tooltip")

        # Placeholders: $input-placeholder-color (bootstrap_overridden.scss:306)
        # over a transparent input (web/static/src/scss/primary_variables
        # .scss:169), so the view is the ground. 4.5:1 dark against 14.3:1 for
        # body text; the light value is upstream's own mix, unchanged.
        self.assertIn("::placeholder{color: #7a818e; opacity: 1;}", dark,
                      "the dark placeholder is not legible on the dark view")
        self.assertIn("::placeholder{color: #b7bcc5; opacity: 1;}", light,
                      "the light placeholder moved")

        # Color scheme: the only declaration that reaches scrollbars, native
        # <select> popups and date pickers (web/static/src/scss/primary_
        # variables.scss:13, emitted at webclient.scss:2 and :27).
        self.assertIn("--o-webclient-color-scheme:dark;", dark, "the dark bundle still declares a bright UA scheme")
        self.assertIn("color-scheme: dark;", dark, "the dark web client still declares a bright UA scheme")
        self.assertIn("--o-webclient-color-scheme:bright;", light)
        self.assertNotIn("--o-webclient-color-scheme:dark;", light)

        # Headings: $o-main-headings-color is $o-black in every scheme upstream
        # (primary_variables.scss:122 -> $headings-color, bootstrap_overridden
        # .scss:135), which on the dark view is ink on ink.
        self.assertIn("--heading-color: #f3f4f6;", dark, "dark headings are still painted black")
        self.assertIn("--heading-color: #000000;", light, "the light heading color moved")

        # Group separator: $table-group-separator-color is $gray-200
        # (bootstrap_overridden.scss:146), which in this scheme is the view
        # itself, so the divider would be drawn in the color it divides.
        divider = self._rule_bodies(dark, ".table-group-divider")
        self.assertTrue(divider, "no .table-group-divider rule in the dark bundle")
        self.assertTrue(any("#1f2937" in body for body in divider),
                        "the dark group divider is not drawn in the scheme's rule color")
        self.assertFalse(any("#111827" in body for body in divider),
                         "the dark group divider is drawn in the view color it separates")

    # --- Web-client chrome ---------------------------------------------
    # The neutral ramp as static/src/scss/primary_variables.scss declares it,
    # and as static/src/scss/primary_variables.dark.scss walks it back the
    # other way. Nine steps, one family; the anchors (hairline, graphite, ink
    # light; ground, view, rule dark) are commented in both files.
    #
    # Read from BRAND, never restated here: four of the eighteen steps are
    # brand values under another name (hairline, graphite, ink, and the three
    # dark anchors), so a literal copy in this file would be a third place for
    # them to drift. brand.py derives the dark ramp from the light one, which
    # is why only one tuple is spelled out there either.
    _RAMP = tuple(c.lower() for c in BRAND["ramp"])
    _RAMP_DARK = tuple(c.lower() for c in BRAND["dark"]["ramp"])

    def _bundle_css(self, name):
        """One bundle's compiled sheet, lowercased.

        Same route as test_dark_scheme_overrides_the_tokens: no session and no
        HTTP round trip, so what is pinned is what the bundle compiles to
        rather than what one page happened to link.
        """
        bundle = self.env["ir.qweb"]._get_asset_bundle(name, css=True, js=False)
        return bundle.css().raw.decode().lower()

    @staticmethod
    def _rule_bodies(css, selector):
        """Every declaration block compiled for exactly `selector`."""
        pattern = re.escape(selector) + r"\{([^{}]*)\}"
        return [m.group(1) for m in re.finditer(pattern, css)]

    @staticmethod
    def _media_block_spans(css):
        """(start, end) of every @media block in the bundle, by brace matching.

        The same reason the lg-only version of this helper existed, asked the
        other way round. rfind("@media", 0, offset) finds the nearest @media
        TEXT before a rule, which is not the same as the block CONTAINING it:
        the compiled bundle holds dozens of already-closed Bootstrap media
        blocks, so a rule is almost always preceded by one it has nothing to do
        with. That heuristic used to report "inside lg" for a rule that had
        been lifted out of its media query; it would now report "media-gated"
        for every unconditional rule in the file. Matching braces is the only
        way to ask the question that actually matters.

        Every condition is collected, not just lg. The band is the page at
        every width, so the invariant is no longer "inside this breakpoint" but
        "inside none of them", and a `max-width` query would break it exactly
        as an `lg` one would.
        """
        spans = []
        for opener in re.finditer(r"@media([^{]*)\{", css):
            depth, index = 1, opener.end()
            while index < len(css) and depth:
                if css[index] == "{":
                    depth += 1
                elif css[index] == "}":
                    depth -= 1
                index += 1
            spans.append((opener.end(), index))
        return spans

    def _assert_not_media_gated(self, css, offset, message):
        spans = self._media_block_spans(css)
        # Not an assertion about the bundle so much as about this helper: a
        # bundle with no media blocks at all would make every call below pass
        # without looking at anything.
        self.assertTrue(spans, "the bundle carries no media query at all")
        self.assertFalse(any(start <= offset < end for start, end in spans), message)

    def test_neutral_ramp_reaches_both_schemes(self):
        """Nine steps light, nine steps dark, each through a named consumer.

        A bare `assertIn(hex, css)` per step proves nothing: four of the nine
        light steps are colors this theme also sets by another name (#e5e7eb is
        $border-color, #9ca3af is $o-colors[0], #4b5563 is $o-brand-secondary,
        #0f172a is $o-main-text-color), so deleting the ramp outright would
        still leave those four assertions green.

        `--gray-<step>` is the consumer that cannot be satisfied by accident.
        Bootstrap emits one per entry of $grays in :root
        (web/static/lib/bootstrap/scss/_root.scss:13-15) under an empty
        $variable-prefix (web/static/src/scss/bootstrap_overridden.scss:51), and
        $grays is built from $gray-N <- $o-gray-N (bootstrap_overridden.scss:
        19-27). Drop a step from our sheet and that property carries upstream's
        Bootstrap grey instead of ours.

        `.btn-secondary` is the second consumer, and the one that makes the ramp
        load-bearing rather than merely present: upstream builds its map out of
        $o-gray-300/-400/-900 (web/static/src/scss/primary_variables.scss:
        247-257). The dark pair is the point of the inversion -- carry the light
        ramp into that bundle unchanged and this button is a near-white slab
        captioned in near-black.
        """
        light = self._bundle_css("web.assets_web")
        dark = self._bundle_css("web.assets_web_dark")
        for step, color in zip(range(100, 1000, 100), self._RAMP):
            self.assertIn(f"--gray-{step}: {color};", light,
                          f"$o-gray-{step} does not reach the light sheet as {color}")
        for step, color in zip(range(100, 1000, 100), self._RAMP_DARK):
            self.assertIn(f"--gray-{step}: {color};", dark,
                          f"dark $o-gray-{step} does not reach the dark sheet as {color}")

        light_btn = self._rule_bodies(light, ".btn-secondary")
        self.assertTrue(light_btn, "no .btn-secondary rule in the light bundle")
        self.assertTrue(
            any("--btn-bg: #e5e7eb" in body and "--btn-color: #0f172a" in body for body in light_btn),
            "the secondary button is not drawn from the AFENDA ramp",
        )
        dark_btn = self._rule_bodies(dark, ".btn-secondary")
        self.assertTrue(dark_btn, "no .btn-secondary rule in the dark bundle")
        self.assertTrue(
            any("--btn-bg: #1f2937" in body and "--btn-color: #f3f4f6" in body for body in dark_btn),
            "the dark secondary button did not invert with the ramp",
        )
        # Upstream hard-codes `hover-color: $o-black` in all three button maps
        # (:253, :266, :283); primary_variables.dark.scss restates the maps to
        # take that out, which the ramp on its own cannot do. Asserted from both
        # ends: the light bundle keeps upstream's map, so it is what proves
        # "#000000" is the literal Sass emits for $o-black -- without it the
        # absence below could be satisfied by a different spelling rather than
        # by the fix.
        self.assertTrue(
            any("--btn-hover-color: #000000" in body for body in light_btn),
            "the light secondary button no longer hovers to $o-black, so the "
            "dark assertions below no longer pin anything",
        )
        for body in dark_btn:
            self.assertNotIn("--btn-hover-color: #000000", body,
                             "a dark button still hovers to black text")
        self.assertTrue(
            any("--btn-hover-color: #f3f4f6" in body for body in dark_btn),
            "the dark secondary button does not hover to the ramp's text step",
        )

    def test_chrome_tokens_reach_the_backend_bundle(self):
        """Navbar, control panel and list: the band structure of the shell.

        Navbar and control panel are set entirely through the tokens their own
        variables files expose (navbar.variables.scss, control_panel.
        variables.scss), so asserting the compiled rule is what proves the
        token was the lever. The list has no variables file, so its two rules
        live in backend.scss and are pinned here beside them.
        """
        light = self._bundle_css("web.assets_web")
        dark = self._bundle_css("web.assets_web_dark")

        # Navbar: 48px bar, and the 14px reading size it inherits from
        # $o-font-size-base. Same geometry in both schemes.
        navbar = self._rule_bodies(light, ".o_main_navbar")
        self.assertTrue(
            any("--o-navbar-height: 48px" in body and "font-size: 0.875rem" in body for body in navbar),
            "the navbar is not on the AFENDA height and type scale",
        )
        # Asserted through the navbar's own custom property rather than the
        # bare rgba, which any module could coincidentally emit. _rule_bodies
        # is not usable here: the entry colour reaches the sheet through
        # @extend placeholders (web/static/src/webclient/navbar/
        # navbar.variables.scss:45-48), so it compiles into grouped selector
        # lists rather than a block that starts with one selector.
        # Lowercased: _bundle_css returns .raw.decode().lower(), so the custom
        # property's camel case does not survive into the haystack.
        self.assertIn(
            "var(--navbar-entry-color, rgba(255, 255, 255, 0.72))", light,
            "the navbar entries are not drawn as a film of their own ground",
        )

        # Control panel: a paper band over a white sheet, ruled with the
        # hairline. Both tokens derive from $o-webclient-background-color and
        # $border-color, so the dark half of this assertion is also what proves
        # the derivation holds -- nothing restates them in the dark file.
        panel = self._rule_bodies(light, ".o_control_panel")
        self.assertTrue(
            any(f"background-color: {BRAND['paper'].lower()}" in body
                and f"1px solid {BRAND['hairline'].lower()}" in body for body in panel),
            "the control panel is not the AFENDA paper band",
        )
        panel_dark = self._rule_bodies(dark, ".o_control_panel")
        self.assertTrue(
            any(f"background-color: {BRAND['dark']['background'].lower()}" in body
                and f"1px solid {BRAND['dark']['border'].lower()}" in body for body in panel_dark),
            "the control panel did not follow the dark ground and rule",
        )

        # List: the column head recedes to graphite and gains weight, and the
        # data cell carries the row rhythm. Read from the ramp, not from
        # $o-brand-secondary, so the head inverts with the scheme.
        for css, head_color, scheme in (
            (light, BRAND["ramp"][6].lower(), "light"),      # graphite, step 700
            (dark, BRAND["dark"]["ramp"][6].lower(), "dark"),
        ):
            heads = self._rule_bodies(css, ".o_list_renderer .o_list_table thead th")
            self.assertTrue(
                any("font-weight: 600" in body and head_color in body for body in heads),
                f"the {scheme} list header is not the AFENDA column head",
            )
            cells = self._rule_bodies(css, ".o_list_renderer .o_list_table .o_data_row > .o_data_cell")
            self.assertTrue(
                any("padding-top: .375rem" in body for body in cells),
                f"the {scheme} list lost its row rhythm",
            )

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

    def _assert_mark_leads(self, tree, xmlid):
        """The AFENDA mark leads the layout instead of trailing it.

        Three claims together, because each alone would still pass with the
        mark back in the footer or loose in a div:

          * it is inside a table cell -- Outlook renders HTML through Word,
            which lays out tables and not divs, which is why this whole
            surface is table-based;
          * the document carries exactly one;
          * nothing mail itself emits -- neither the call to action nor the
            message body -- precedes it in document order.

        The last is the one that actually pins it to the header. An assertion
        that the mark is merely *present* passed for the whole time it lived
        in the footer, which is what made it worth nothing here.
        """
        marks = tree.xpath("//img[contains(@src, '/afenda_brand/static/img/logo_email_2x.png')]")
        self.assertEqual(len(marks), 1, f"{xmlid} does not carry exactly one AFENDA mark")
        mark = marks[0]
        self.assertEqual(mark.getparent().tag, "td", f"{xmlid}: the mark is not in a table cell")
        order = {node: index for index, node in enumerate(tree.iter())}
        # The CTA cell and the message body: one per layout branch, both
        # emitted by mail's own markup and never by ours.
        trailing = tree.xpath("//td[a[@href='/x']]") + tree.xpath("//p[normalize-space()='body']")
        self.assertEqual(len(trailing), 2, f"{xmlid} rendered neither the CTA nor the body")
        for node in trailing:
            self.assertLess(
                order[mark], order[node],
                f"{xmlid}: the mark does not lead the layout",
            )
        return mark

    def test_the_token_files_invent_no_colour(self):
        """Every hex literal in the module's SCSS is one BRAND declares.

        Scope deliberately stated: this catches hex LITERALS, not colours.
        A value reached through mix(), darken(), rgba() or a CSS keyword is
        computed at build time and never appears here as text -- the dark
        placeholder is exactly that (a mix of two ramp steps, compiling to a
        value BRAND does not name). Widening this to "every colour" would mean
        compiling both bundles and diffing every declaration, a different and
        much slower test. What this one buys is that the cheapest way to
        introduce a colour -- typing one -- is closed.

        `.claude/odoo-agent-rules.md` puts brand values in brand.py and mirrors
        them into primary_variables.scss, because SCSS cannot import Python --
        "the mirroring is the point". Nothing enforced the mirror in the
        direction that actually drifts: a token file is where a new colour gets
        invented, one hex at a time, each individually defensible. This asserts
        the closed set rather than any single value, so the failure arrives at
        the moment a colour is introduced instead of months later when someone
        notices three greys that are nearly the same.

        Comments are stripped first: they quote upstream's own values (the
        Bootstrap warm ramp, $o-black) to explain what is being overridden, and
        those are prose about foreign colours, not declarations of ours.
        """
        allowed = set()

        def collect(value):
            if isinstance(value, str):
                if re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
                    allowed.add(value.lower())
            elif isinstance(value, dict):
                for item in value.values():
                    collect(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    collect(item)

        collect(BRAND)
        # Not a floor on taste, just proof BRAND imported and was walked: an
        # empty `allowed` would make every comparison below come back clean.
        self.assertTrue(allowed, "no colours collected from BRAND")

        def expand(literal):
            """#abc -> #aabbcc, #rrggbbaa -> #rrggbb, so all forms compare."""
            digits = literal.lower().lstrip("#")
            if len(digits) == 3:
                digits = "".join(digit * 2 for digit in digits)
            return "#" + digits[:6]

        # Every SCSS file the module ships, not only the two token files: the
        # rule is about brand values the product uses, and login.scss and
        # backend.scss are just as able to invent one.
        for name in ("primary_variables.scss", "primary_variables.dark.scss",
                     "login.scss", "backend.scss"):
            with file_open(f"afenda_brand/static/src/scss/{name}", "r") as handle:
                source = handle.read()
            code = re.sub(r"//[^\n]*", "", source)
            # base-2 is upstream's editor palette, kept verbatim on purpose
            # (base-1 beside it is ours); it is the one place foreign colours
            # are the correct answer.
            code = re.sub(r"'base-2':\s*\((?:[^()]|\([^()]*\))*\)", "", code)
            found = {expand(h) for h in re.findall(r"#[0-9A-Fa-f]{3,8}", code)}
            stray = sorted(found - allowed)
            self.assertFalse(
                stray,
                f"{name} uses {stray} which BRAND does not declare; add it to brand.py "
                f"with a name and a reason, or express it from a value already there",
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
        Verdana on Odoo's #454748, and without the header row the AFENDA mark
        is either in the footer or not there at all."""
        html = self._render_email_layout("mail.mail_notification_layout")
        tree = lxml_html.fromstring(html)
        body = tree.xpath("//body")[0].get("style")
        self.assertIn("Source Sans 3", body)
        self.assertNotIn("Verdana", body)
        self.assertIn(BRAND["ink"], body)
        self._assert_mark_leads(tree, "mail.mail_notification_layout")
        # What the move actually bought, and the one thing a footer mark could
        # never satisfy: upstream's "Powered by" block is gated on show_footer,
        # so a message with neither header nor footer used to carry no AFENDA
        # at all. The header row is ungated.
        bare = self._render_email_layout(
            "mail.mail_notification_layout",
            email_notification_force_header=False,
            email_notification_allow_header=False,
            email_notification_force_footer=False,
            email_notification_allow_footer=False,
            has_button_access=False,
        )
        self.assertIn(
            "/afenda_brand/static/img/logo_email_2x.png", bare,
            "the mark vanishes on a message with neither header nor footer",
        )
        # Nothing outbound, and no orphaned wording left behind by removing it.
        self.assertNotIn("utm_source=db", html, "the outbound 'Powered by' link survived")
        self.assertNotIn("Powered by", html, "the 'Powered by' wording survived the anchor")
        self.assertIn("The truth of your business, kept.", html, "the footer sign-off is gone")
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
        # Anchored on upstream's own padding rather than on "font-size:11px",
        # which the replaced "Powered by" cell below now also carries.
        footer = tree.xpath("//td[contains(@style, 'padding: 0 8px 0 8px')]")[0].get("style")
        self.assertIn(f"border-top:1px solid {BRAND['hairline']}", footer)
        self.assertEqual(self._last_color(footer), BRAND["graphite"])
        self._assert_mark_leads(tree, "mail.mail_notification_light")
        # Pinned to the structure the brief names: the first <tr> of the card's
        # own <tbody>, above upstream's record-name HEADER row.
        rows = tree.xpath("//table[@width='590']/tbody/tr")
        self.assertTrue(rows, "the card lost its rows")
        self.assertEqual(
            len(rows[0].xpath(".//img[contains(@src, 'logo_email_2x.png')]")), 1,
            "the AFENDA mark is not in the first row of the card",
        )
        self.assertNotIn("Powered by", html, "the 'Powered by' wording survived the anchor")
        self.assertIn("The truth of your business, kept.", html, "the footer sign-off is gone")
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

    def test_email_header_carries_both_marks(self):
        """The header is a letterhead: the tenant's logo as the subject, ours
        as the maker's mark, in that order and at that ratio.

        The `?company=` is the load-bearing part. /web/binary/company_logo
        takes the company from the query string when it is there and otherwise
        falls back to `request.session.uid or SUPERUSER_ID` and reads THAT
        user's company (addons/web/controllers/binary.py:264-287). A mail
        client fetches the image with no Odoo session, so dropping the
        parameter serves the superuser's company logo to every recipient on a
        multi-company database -- and the right one on a single-company
        database, which is exactly why this needs a test and not a reading.

        The absent `width` is deliberate, not an omission: logo_web is
        `image_process(logo, size=(180, 0))`
        (odoo/addons/base/models/res_company.py:169-172), at most 180 wide with
        a free height, so the aspect ratio is unknown at render time and any
        fixed width/height pair would squash somebody's logo. Height fixed,
        width free is the only non-distorting contract available.
        """
        tenant = self.env["res.company"].create(
            {"name": "Tenant Co", "logo": _png_b64((9, 9, 9))}
        )
        # The premise: this logo does not read as the shipped default. If it
        # ever did, every assertion below would pass vacuously.
        self.assertFalse(tenant.uses_default_logo, "the premise failed: this logo reads as default")
        for xmlid in ("mail.mail_notification_layout", "mail.mail_notification_light"):
            html = self._render_email_layout(xmlid, company=tenant)
            tree = lxml_html.fromstring(html)
            logos = tree.xpath("//img[contains(@src, '/web/binary/company_logo')]")
            self.assertEqual(len(logos), 1, f"{xmlid} does not carry the tenant logo exactly once")
            logo = logos[0]
            self.assertIn(
                f"company={tenant.id}", logo.get("src"),
                f"{xmlid}: no explicit ?company=, so a session-less fetch picks the wrong one",
            )
            self.assertTrue(
                logo.get("src").startswith("http"),
                f"{xmlid}: the tenant logo URL is relative and an email has no origin",
            )
            # Most clients block remote images, so for many recipients the alt
            # text IS the header. Upstream's generic "Logo" would be noise.
            self.assertEqual(
                logo.get("alt"), "Tenant Co",
                f"{xmlid}: a blocked-image header would name no company",
            )
            self.assertEqual(logo.get("height"), "32", f"{xmlid}: no height attribute for Outlook")
            self.assertIsNone(
                logo.get("width"),
                f"{xmlid}: a fixed width distorts a logo whose aspect ratio is unknown",
            )
            self.assertEqual(logo.getparent().tag, "td", f"{xmlid}: the tenant logo is not in a cell")
            # Upstream's light layout draws its own copy beside the record name
            # (mail_templates_email_layouts.xml:126-128); it has to be gone, or
            # the tenant appears twice and after us instead of before.
            self.assertNotIn(
                "/logo.png?company", html, f"{xmlid} carries a second copy of the tenant logo",
            )
            mark = tree.xpath("//img[contains(@src, 'logo_email_2x.png')]")[0]
            order = {node: index for index, node in enumerate(tree.iter())}
            self.assertLess(order[logo], order[mark], f"{xmlid}: our mark precedes the tenant's")
            self.assertLess(
                int(mark.get("height")), int(logo.get("height")),
                f"{xmlid}: our mark is not the smaller of the two",
            )

    def test_email_header_omits_a_logo_the_tenant_never_set(self):
        """A company with no artwork of its own must emit no tenant <img>.

        /web/binary/company_logo falls through to web/static/img/nologo.png, a
        180x79 fully transparent plate (binary.py:305). On a page that is a
        blank space; in a mail client with images blocked it is a broken-image
        icon next to an alt string, which is worse than nothing.
        `uses_default_logo` is `not company.logo or company.logo ==
        default_logo` (res_company.py:179-182), so gating on it covers the
        no-logo case AND the case where the tenant is still showing AFENDA's
        own shipped mark -- which must never pose as theirs beside ours.
        """
        bare = self.env["res.company"].create({"name": "No Logo Co"})
        bare.logo = False
        self.assertTrue(bare.uses_default_logo, "the premise failed: this company has a logo")
        for xmlid in ("mail.mail_notification_layout", "mail.mail_notification_light"):
            html = self._render_email_layout(xmlid, company=bare)
            self.assertNotIn(
                "/web/binary/company_logo", html,
                f"{xmlid} links artwork the tenant never set",
            )
            self.assertIn(
                "/afenda_brand/static/img/logo_email_2x.png", html,
                f"{xmlid} dropped the AFENDA mark along with the tenant's",
            )

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
