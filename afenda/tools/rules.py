"""Ordered phase-1 rules. Later rules see the output of earlier ones."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from afenda.tools.rebrand import Rule

MARKUP = frozenset({".xml", ".html", ".js", ".ts", ".po", ".pot", ".md", ".rst", ".json", ".csv"})
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
        # 1. Legal name in user-facing markup and translations only.
        Rule("company_name", re.compile(r"Odoo S\.A\."), short, suffixes=MARKUP),
        # 2. The system bot.
        Rule("bot", re.compile(r"OdooBot"), bot),
        # 3. Documentation links become same-origin generated docs.
        Rule(
            "docs_link",
            re.compile(r"https?://(?:www\.)?odoo\.com/documentation/(?:\d+\.\d+|latest|master|saas-[\d.]+)/?"),
            docs,
        ),
        # 4. Every other odoo.com host or address.
        Rule("odoo_com", re.compile(r"\bodoo\.com\b"), domain),
        # 5. Browser address prefix. Not filesystem paths (/home/odoo), not the IoT image.
        Rule(
            "url_prefix",
            re.compile(r"(?<![\w.])/odoo(?=[/'\"`?#\s)\]]|$)"),
            f"/{prefix}",
            suffixes=URLISH,
            path_excludes=("iot_box_image",),
        ),
        Rule("router_prefix", re.compile(r'"odoo"'), f'"{prefix}"', path_contains=(ROUTER,)),
        # 6. The product name, standalone word only, last so earlier rules win.
        Rule("product", re.compile(r"(?<![\w\-@/.])Odoo(?![\w\-])"), product),
    ]


RULES: list[Rule] = build_rules(load_brand())
