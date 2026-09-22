import re

from markupsafe import Markup

from odoo.tests import TransactionCase, tagged

STYLE = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)


@tagged("post_install", "-at_install")
class TestDigestLayout(TransactionCase):
    """The digest email carries the AFENDA cascade, not Odoo's."""

    def _render_layout(self):
        """Render the digest layout the way digest does.

        `digest._action_send_to_user` builds the body from
        `digest.digest_mail_main` and then wraps it with `_render_encapsulate`
        on `digest.digest_mail_layout` (addons/digest/models/digest.py:185-192).
        Only the wrapper carries the <style> blocks, so that is what is
        rendered here.
        """
        digest = self.env.ref("digest.digest_digest_default")
        return self.env["mail.render.mixin"]._render_encapsulate(
            "digest.digest_mail_layout",
            Markup("<p>digest body</p>"),
            add_context={"company": self.env.company, "user": self.env.user},
            context_record=digest,
        )

    def test_digest_layout_appends_afenda_style(self):
        """Regression: afenda_brand_digest not installed, or its xpath no
        longer matching `//style`, leaves the digest with upstream's single
        block and Odoo's link color."""
        html = self._render_layout()
        blocks = STYLE.findall(html)
        self.assertEqual(
            len(blocks), 2, "the AFENDA style block was not appended to the digest layout"
        )
        self.assertIn("a { color: #1E3A8A", blocks[-1])
        self.assertIn("body { color: #0F172A !important; }", blocks[-1])
        # Ours must be the last one: the digest layout has no specificity
        # story, only source order.
        self.assertGreater(
            html.rindex("a { color: #1E3A8A"),
            html.index("</style>"),
            "the AFENDA block must follow upstream's, or it loses the cascade",
        )
        self.assertIn("#1E3A8A", html)

    def test_digest_layout_keeps_upstream_rules(self):
        """Regression: replacing upstream's <style> instead of appending would
        strip the layout rules the digest body depends on."""
        blocks = STYLE.findall(self._render_layout())
        self.assertIn(".global_layout", blocks[0])
        self.assertIn("@media only screen", blocks[0])
