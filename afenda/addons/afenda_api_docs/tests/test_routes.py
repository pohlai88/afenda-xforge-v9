import re

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestDocsRoutes(HttpCase):
    def test_landing_is_public_and_branded(self):
        res = self.url_open("/docs")
        self.assertEqual(res.status_code, 200)
        self.assertIn("AFENDA", res.text)

    def test_landing_links_do_not_bounce_back_to_the_landing_page(self):
        # The redirect in docs_landing() sends any subpath naming no guide
        # straight back to `/docs`. That is correct for a stray in-product
        # link, but a link the landing page itself renders must not point
        # at a subpath that does the same thing - that would put a link on
        # the page whose only effect is returning the visitor to the page
        # they are already on. This is the check test_routes.py lacked
        # before: the existing redirect test above only exercises an
        # unrelated hard-coded path, never the landing page's own <a>
        # elements.
        landing = self.url_open("/docs")
        hrefs = re.findall(r'href="(/docs/[^"]*)"', landing.text)
        for href in hrefs:
            res = self.url_open(href, allow_redirects=False)
            bounces_home = (
                res.status_code == 303 and res.headers.get("Location") == "/docs"
            )
            self.assertFalse(
                bounces_home,
                "landing page link %r redirects straight back to /docs" % href,
            )

    def test_landing_carries_no_odoo_identity(self):
        res = self.url_open("/docs")
        for tell in ("Odoo", "odoo.com"):
            self.assertNotIn(tell, res.text)

    def test_guide_url_renders_its_guide(self):
        # "applications/general/users.md" -> template id
        # "guide_applications_general_users", per build_docs.py:slug_for.
        res = self.url_open("/docs/applications/general/users")
        self.assertEqual(res.status_code, 200)
        self.assertIn("<h1>Users and access rights</h1>", res.text)

    def test_subpath_without_a_guide_redirects_to_the_index(self):
        # A real in-product path with no guide generated for it yet (this
        # one appears in addons/auth_totp*/views/templates.xml and friends).
        # It must not 404 - most `/docs/applications/...` links in the tree
        # have no guide generated so far, so 404ing here would break most
        # in-product documentation links, not just a hypothetical broken
        # one. It must also not render the landing page inline at this URL:
        # that would silently claim to be a guide it is not. A redirect to
        # `/docs` is neither: the address bar visibly changes, so the user
        # can see they did not land on what they asked for.
        res = self.url_open(
            "/docs/applications/general/auth/2fa.html", allow_redirects=False
        )
        self.assertEqual(res.status_code, 303)
        self.assertEqual(res.headers["Location"], "/docs")
