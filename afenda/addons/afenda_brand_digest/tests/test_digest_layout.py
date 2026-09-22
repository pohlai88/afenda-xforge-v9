import re

from lxml import html as lxml_html

from odoo.tests import TransactionCase, tagged

STYLE = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)
SIMPLE_SELECTOR = re.compile(r"([a-zA-Z][\w-]*)?((?:[#.][\w-]+)*)")


def _rules(css):
    """[(selector, declaration-block)] in source order.

    Enough of a CSS parser for these two blocks: no library is vendored with
    Odoo. `@media` blocks are skipped rather than flattened -- they are
    width-conditional, so they say nothing about how the email renders on a
    desktop client.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    out, i, n = [], 0, len(css)
    while i < n:
        brace = css.find("{", i)
        if brace < 0:
            break
        selector = css[i:brace].strip()
        depth, end = 1, brace + 1
        while end < n and depth:
            depth += {"{": 1, "}": -1}.get(css[end], 0)
            end += 1
        if not selector.startswith("@"):
            out.append((selector, css[brace + 1:end - 1]))
        i = end
    return out


def _declarations(block):
    """{property: (value, is_important)}"""
    found = {}
    for piece in block.split(";"):
        prop, sep, value = piece.partition(":")
        if not sep:
            continue
        value = value.strip()
        important = value.lower().endswith("!important")
        if important:
            value = value[: -len("!important")].strip()
        found[prop.strip().lower()] = (value, important)
    return found


def _specificity(selector, element):
    """Highest specificity with which `selector` matches, or None."""
    tag = element.tag if isinstance(element.tag, str) else ""
    classes = set((element.get("class") or "").split())
    element_id = element.get("id")
    best = None
    for part in selector.split(","):
        match = SIMPLE_SELECTOR.fullmatch(part.strip())
        if not match:
            continue  # a combinator or pseudo: out of scope, and unused here
        name, rest = match.group(1), match.group(2) or ""
        if name and name.lower() != tag.lower():
            continue
        ids = re.findall(r"#([\w-]+)", rest)
        names = re.findall(r"\.([\w-]+)", rest)
        if any(one != element_id for one in ids) or any(one not in classes for one in names):
            continue
        spec = (len(ids), len(names), 1 if name else 0)
        best = spec if best is None or spec > best else best
    return best


def resolved_color(rules, element):
    """The colour an email client paints `element` with, or None.

    Walks the real cascade: the inline `style` attribute, then every matching
    rule ranked by importance, then specificity, then source order; and up the
    ancestors when nothing on the element itself sets a colour.
    """
    node = element
    while node is not None:
        best = None
        inline = _declarations(node.get("style") or "").get("color")
        if inline:
            best = ((1 if inline[1] else 0, (1, 0, 0), -1), inline[0])
        for order, (selector, block) in enumerate(rules):
            declaration = _declarations(block).get("color")
            if not declaration:
                continue
            spec = _specificity(selector, node)
            if spec is None:
                continue
            key = (1 if declaration[1] else 0, spec, order)
            if best is None or key > best[0]:
                best = (key, declaration[0])
        if best:
            return best[1].strip().upper()
        node = node.getparent()
    return None


@tagged("post_install", "-at_install")
class TestDigestLayout(TransactionCase):
    """The digest email carries the AFENDA cascade, not Odoo's."""

    def _digest_email(self):
        """The real thing: `digest._action_send_to_user` renders
        `digest.digest_mail_main` and wraps it with `_render_encapsulate` on
        `digest.digest_mail_layout` (addons/digest/models/digest.py:185-192).
        Only a full render has the elements the <style> blocks select.
        """
        reader = self.env["res.users"].create(
            {"name": "Digest Reader", "login": "digest@example.com", "email": "digest@example.com"}
        )
        digest = self.env.ref("digest.digest_digest_default")
        digest._action_send_to_user(reader, tips_count=1, consume_tips=False)
        mail = self.env["mail.mail"].search(
            [("email_to", "like", "digest@example.com")], order="id desc", limit=1
        )
        self.assertTrue(mail, "the digest produced no email")
        return mail.body_html

    def test_digest_layout_appends_afenda_style(self):
        """Regression: afenda_brand_digest not installed, or its xpath no
        longer matching the namespaced `//style`, leaves the digest with
        upstream's single block."""
        blocks = STYLE.findall(self._digest_email())
        self.assertEqual(
            len(blocks), 2, "the AFENDA style block was not appended to the digest layout"
        )
        # Ours last: the digest has no specificity story, only source order.
        self.assertIn("#1E3A8A", blocks[-1])
        self.assertIn(".global_layout", blocks[0], "upstream's block was replaced, not kept")
        self.assertIn("@media only screen", blocks[0], "upstream's block was replaced, not kept")

    def test_digest_text_resolves_to_afenda_colors(self):
        """The assertion that fails on *effect*: each element below is resolved
        through the real cascade, and the expected colour is checked to differ
        from what upstream's own block gives it. Drop the AFENDA block, or aim
        it at a selector that carries no colour (`a`, whose every child span
        sets its own), and every one of these reverts to the Odoo grey.
        """
        html = self._digest_email()
        tree = lxml_html.fromstring(html)
        blocks = STYLE.findall(html)
        upstream_only = _rules(blocks[0])
        everything = [rule for block in blocks for rule in _rules(block)]

        for css_class, expected in (
            # "Sent by"/"Powered by" line: upstream #878D97.
            ("by_odoo", "#4B5563"),
            # The KPI figures: upstream #374151 both as a class rule and as an
            # inline style on the span, so this one also proves the !important
            # beats an inline declaration.
            ("kpi_value", "#0F172A"),
            ("header_title", "#0F172A"),
            ("kpi_value_label", "#4B5563"),
        ):
            elements = tree.xpath(f"//*[contains(concat(' ', @class, ' '), ' {css_class} ')]")
            self.assertTrue(elements, f"the digest rendered no .{css_class} element")
            element = elements[0]
            before = resolved_color(upstream_only, element)
            after = resolved_color(everything, element)
            self.assertIsNotNone(before, f".{css_class} has no colour at all upstream")
            self.assertNotEqual(
                before,
                expected.upper(),
                f".{css_class} is already {expected} upstream, so this proves nothing",
            )
            self.assertEqual(
                after,
                expected.upper(),
                f".{css_class} resolves to {after}, not the AFENDA {expected}",
            )
