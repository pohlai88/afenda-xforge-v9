"""Brand aliasing for generated documentation.

Two classes of string appear in a generated document and they must never be
treated alike:

* **Prose** - summaries, descriptions, field labels and help, selection
  labels, docstrings. Always aliased.
* **Wire values** - model, field, method and parameter names, selection keys,
  spreadsheet function names such as ODOO.BALANCE. Never aliased: a caller
  must send them back verbatim, so renaming one documents an API that
  rejects its own documentation.

The split is enforced structurally, by calling `alias_prose` only at prose
insertion points, never by scanning an assembled document.

Unlike the build-time rules in `afenda/tools/rules.py`, matching here is
case-insensitive on the standalone word: those rules must spare lowercase
`odoo` because a source file contains imports, license headers and module
paths. A prose field contains none of those. Word boundaries keep this safe
- `\\bodoo\\b` does not match inside `odoobot_state`.
"""
import re

from odoo.addons.afenda_brand.brand import BRAND

# Ordered. Earlier rules win: the legal name and the bot name must be
# consumed before the bare product name would split them.
_RULES = (
    (re.compile(r"Odoo\s+S\.A\.", re.IGNORECASE), BRAND["short"]),
    (re.compile(r"\bOdooBot\b", re.IGNORECASE), BRAND["bot"]),
    (
        re.compile(
            r"https?://(?:www\.)?odoo\.com"
            r"/documentation(?:/(?:\d+\.\d+|latest|master|saas-[\d.]+))?/?",
            re.IGNORECASE,
        ),
        BRAND["docs_path"],
    ),
    (re.compile(r"\bodoo\.com\b", re.IGNORECASE), BRAND["domain"]),
    (re.compile(r"\bodoo\b", re.IGNORECASE), BRAND["product"]),
)


def alias_prose(text):
    """Rewrite Odoo identity in a prose string. Never call this on a wire value."""
    if not text:
        return text
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text
