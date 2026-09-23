"""Ordered phase-1 rules. Later rules see the output of earlier ones."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from afenda.tools.rebrand import Rule

# Domains an earlier AFENDA release shipped and has since moved off. Only the
# domain that actually shipped goes here, hard-coded and literal -- that is
# deliberate, not an oversight: a superseded value is a fixed historical fact,
# never the current brand value (contrast `domain` in build_rules below, which
# is read from BRAND precisely because it *does* change). Never add an entry
# whose compiled pattern would match the current domain -- build_rules raises
# if it does, because that would make the rule below match its own
# replacement and loop forever. Note this is broader than "never list the
# current domain verbatim": e.g. listing "nexuscanon.com" here while the
# current domain is "app.nexuscanon.com" would still match (see build_rules).
# Migration-local, in the same sense as afenda_brand/hooks.py's
# _SUPERSEDED_EMAIL_COLORS: delete the entry (and, once the tuple is empty,
# the rule itself) once no tree still carries the old value.
_SUPERSEDED_DOMAINS = ("afenda.app",)

MARKUP = frozenset({".xml", ".html", ".js", ".ts", ".po", ".pot", ".md", ".rst", ".json", ".csv"})
# Formats whose text is only ever displayed. Excludes .js/.ts/.json/.csv,
# where a quoted ODOO can be an API payload identifier rather than a label.
DISPLAY = frozenset({".xml", ".html", ".po", ".pot", ".md", ".rst"})
URLISH = frozenset({".py", ".js", ".ts", ".xml", ".html", ".md", ".rst", ".po", ".pot", ".json", ".csv"})
ROUTER = "addons/web/static/src/core/browser/router.js"


def load_brand() -> dict:
    path = Path(__file__).resolve().parents[1] / "addons" / "afenda_brand" / "brand.py"
    spec = importlib.util.spec_from_file_location("afenda_brand_values", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BRAND


def build_rules(brand: dict) -> list[Rule]:
    product, short, bot = brand["product"], brand["short"], brand["bot"]
    domain, docs, prefix = brand["domain"], brand["docs_path"], brand["url_prefix"]
    # Impossible-by-construction anti-loop check. Guard on the actual match
    # condition -- the compiled pattern searching the current domain -- not
    # on set membership, which is strictly weaker: a future domain such as
    # "app.nexuscanon.com" is not *in* ("nexuscanon.com",), but the
    # \b-bounded pattern for "nexuscanon.com" still matches inside it
    # (preceded by ".", a non-word character), so a membership-only check
    # would miss it and every `rebrand --apply` would grow the domain another
    # "app." label. Building the pattern once and reusing it for both the
    # guard and the Rule below keeps the two in sync by construction. A raise
    # (not assert) so the guard holds under `python -O` too.
    superseded_domain_pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(d) for d in _SUPERSEDED_DOMAINS) + r")\b",
        re.IGNORECASE,
    )
    if superseded_domain_pattern.search(domain):
        raise ValueError(
            f"BRAND['domain'] ({domain!r}) matches the superseded_domain "
            f"pattern built from _SUPERSEDED_DOMAINS ({_SUPERSEDED_DOMAINS!r}) "
            "-- that would make the rule match its own replacement"
        )
    return [
        # 1. Legal name, everywhere — must run before the standalone "product" rule
        #    (below) or Python manifests get a fabricated "AFENDA xForge S.A.".
        Rule("company_name", re.compile(r"Odoo S\.A\."), short),
        # 2. The system bot.
        Rule("bot", re.compile(r"OdooBot"), bot),
        # 3. Superseded brand domains repaired to the current one. Must run
        #    before docs_link (next) so a stale old-domain documentation link
        #    falls through to /docs/ instead of merely landing on the new
        #    domain as a bare link.
        Rule(
            "superseded_domain",
            # \b excludes word-char-prefixed hosts only, so "notafenda.app"
            # correctly does not match. It does NOT exclude non-word-char
            # prefixes such as "-": "foo-afenda.app" DOES match -- identical
            # to the odoo_com rule's own behaviour below, so this is
            # consistent with existing practice, not a gap introduced here.
            # Do not widen this to a bare substring match.
            superseded_domain_pattern,
            domain,
        ),
        # 4. Documentation links become same-origin generated docs. The version
        #    segment is optional: the web client's documentation_link widget builds
        #    the settings help URL by concatenation, so its literal ends at
        #    "/documentation/" and a version-requiring pattern misses it, leaving
        #    117 settings links to fall through to the odoo_com rule below and
        #    point off-origin. The brand domain is matched alongside odoo.com so
        #    links that already took that fall-through come back to /docs/.
        Rule(
            "docs_link",
            re.compile(
                rf"https?://(?:www\.)?(?:odoo\.com|{re.escape(domain)})"
                r"/documentation(?:/(?:\d+\.\d+|latest|master|saas-[\d.]+))?/?"
            ),
            docs,
        ),
        # 5. Every other odoo.com host or address.
        Rule("odoo_com", re.compile(r"\bodoo\.com\b", re.IGNORECASE), domain),
        # 6. Browser address prefix. Not filesystem paths (/home/odoo), not the IoT image.
        Rule(
            "url_prefix",
            re.compile(r"(?<![\w.])/odoo(?=[/'\"`?#\s)\]]|$)"),
            f"/{prefix}",
            suffixes=URLISH,
            path_excludes=("iot_box_image", "odoo/cli/", "odoo/netsvc.py", "odoo/tests/common.py"),
        ),
        Rule("url_prefix_encoded", re.compile(r"%2Fodoo(?=%2F|['\"]|$)"), f"%2F{prefix}", suffixes=URLISH),
        Rule("router_prefix", re.compile(r'"odoo"'), f'"{prefix}"', path_contains=(ROUTER,)),
        # 7. Social/profile handles at domain root (twitter.com/Odoo).
        Rule("social_handle", re.compile(r"(?<![\w.-])((?:www\.)?(?:twitter|x|facebook|linkedin|instagram|youtube|github|tiktok)\.com/)Odoo(?=[/\"'\s)]|$)"), rf"\g<1>{short.lower()}"),
        # 8. ALL-CAPS product name, markup and translations only. Python and JS
        #    string literals carry API payload identifiers (payment provider
        #    paymentSource, merchant customer ids, EDI request prefixes) that
        #    third parties have registered; rewriting those breaks integrations.
        Rule(
            "product_allcaps",
            re.compile(r"(?<![\w@/.])ODOO(?!\w)"),
            product.upper(),
            suffixes=DISPLAY,
        ),
        # 9. Lowercase standalone word when it is the ENTIRE quoted attribute value
        #    (e.g. title="odoo", placeholder="odoo") — never touches odoo.com-style
        #    text or the "odoo" package name in code, which aren't bare quoted values.
        #    Scoped to markup files only, so it can't collide with quoted "odoo"
        #    string constants in JS/Python (e.g. the router's own prefix constant).
        Rule(
            "product_lowercase_attr",
            re.compile(r'(?<=["\'])odoo(?=["\'])'),
            # Tooltips and placeholders a user reads, so match the wordmark's
            # casing rather than the lowercase identifier form.
            short,
            suffixes=frozenset({".xml", ".html"}),
        ),
        # 10. The product name, standalone word only, last so earlier rules win.
        Rule("product", re.compile(r"(?<![\w@/.])Odoo(?!\w)"), product),
    ]


RULES: list[Rule] = build_rules(load_brand())
