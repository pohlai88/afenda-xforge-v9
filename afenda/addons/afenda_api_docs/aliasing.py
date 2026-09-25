r"""Brand aliasing for generated documentation.

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
paths. A prose field contains none of those.

`\b` alone is not enough to protect a wire value from being split. `\b` is
satisfied by *any* transition between a word character and a non-word
character, and `.` is a non-word character - so plain `\bodoo\b` correctly
skips `odoobot_state` (`_` is a word character, so there is no boundary
there) but happily matches the `ODOO` segment of a dot-delimited token such
as `ODOO.BALANCE` or `res.odoo.field`, because the dots on either side do
supply a `\b`. Rules 2 and 5 below use explicit lookarounds instead:
`(?<![\w.])` on the left and `(?!\w)(?!\.\w)` on the right. The left side
refuses to match when preceded by a word character *or a dot*, so a leading
`.odoo` never matches. The right side refuses both a following word
character and a following `.` that is itself followed by a word character
- that second clause is what blocks `odoo.BALANCE` while still allowing a
sentence-ending period such as "runs on odoo." to alias normally, since a
trailing `.` with nothing (or non-word) after it is not a dotted token.
"""
import re

from odoo.addons.afenda_brand.brand import BRAND

# Ordered. Earlier rules win: the legal name and the bot name must be
# consumed before the bare product name would split them.
_RULES = (
    (re.compile(r"Odoo\s+S\.A\.", re.IGNORECASE), BRAND["short"]),
    (re.compile(r"(?<![\w.])OdooBot(?!\w)(?!\.\w)", re.IGNORECASE), BRAND["bot"]),
    (
        re.compile(
            r"https?://(?:www\.)?odoo\.com"
            r"/documentation(?:/(?:\d+\.\d+|latest|master|saas-[\d.]+))?/?",
            re.IGNORECASE,
        ),
        BRAND["docs_path"],
    ),
    (re.compile(r"\bodoo\.com\b", re.IGNORECASE), BRAND["domain"]),
    (re.compile(r"(?<![\w.])odoo(?!\w)(?!\.\w)", re.IGNORECASE), BRAND["product"]),
)


def alias_prose(text):
    """Rewrite Odoo identity in a prose string. Never call this on a wire value."""
    if not text:
        return text
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text
