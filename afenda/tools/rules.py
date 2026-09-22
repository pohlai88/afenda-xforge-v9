"""Ordered phase-1 rules. Later rules see the output of earlier ones."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from afenda.tools.rebrand import Rule

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
    return [
        # 1. Legal name, everywhere — must run before the standalone "product" rule
        #    (below) or Python manifests get a fabricated "AFENDA xForge S.A.".
        Rule("company_name", re.compile(r"Odoo S\.A\."), short),
        # 2. The system bot.
        Rule("bot", re.compile(r"OdooBot"), bot),
        # 3. Documentation links become same-origin generated docs.
        Rule(
            "docs_link",
            re.compile(r"https?://(?:www\.)?odoo\.com/documentation/(?:\d+\.\d+|latest|master|saas-[\d.]+)/?"),
            docs,
        ),
        # 4. Every other odoo.com host or address.
        Rule("odoo_com", re.compile(r"\bodoo\.com\b", re.IGNORECASE), domain),
        # 5. Browser address prefix. Not filesystem paths (/home/odoo), not the IoT image.
        Rule(
            "url_prefix",
            re.compile(r"(?<![\w.])/odoo(?=[/'\"`?#\s)\]]|$)"),
            f"/{prefix}",
            suffixes=URLISH,
            path_excludes=("iot_box_image", "odoo/cli/", "odoo/netsvc.py", "odoo/tests/common.py"),
        ),
        Rule("url_prefix_encoded", re.compile(r"%2Fodoo(?=%2F|['\"]|$)"), f"%2F{prefix}", suffixes=URLISH),
        Rule("router_prefix", re.compile(r'"odoo"'), f'"{prefix}"', path_contains=(ROUTER,)),
        # 6. Social/profile handles at domain root (twitter.com/Odoo).
        Rule("social_handle", re.compile(r"(?<![\w.-])((?:www\.)?(?:twitter|x|facebook|linkedin|instagram|youtube|github|tiktok)\.com/)Odoo(?=[/\"'\s)]|$)"), rf"\g<1>{short.lower()}"),
        # 7. ALL-CAPS product name, markup and translations only. Python and JS
        #    string literals carry API payload identifiers (payment provider
        #    paymentSource, merchant customer ids, EDI request prefixes) that
        #    third parties have registered; rewriting those breaks integrations.
        Rule(
            "product_allcaps",
            re.compile(r"(?<![\w@/.])ODOO(?!\w)"),
            product.upper(),
            suffixes=DISPLAY,
        ),
        # 8. Lowercase standalone word when it is the ENTIRE quoted attribute value
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
        # 9. The product name, standalone word only, last so earlier rules win.
        Rule("product", re.compile(r"(?<![\w@/.])Odoo(?!\w)"), product),
    ]


RULES: list[Rule] = build_rules(load_brand())
