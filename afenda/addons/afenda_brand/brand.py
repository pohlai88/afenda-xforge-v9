"""Single source of truth for the AFENDA xForge identity (v2.1, 2026-09-22).

Keep in sync with static/src/scss/primary_variables.scss.
"""

import base64

from odoo.tools import file_open

BRAND = {
    "product": "AFENDA xForge",
    "short": "AFENDA",
    "bot": "AFENDA Bot",
    "tagline": "The truth of your business, kept.",
    # Colors
    "primary": "#1E3A8A",  # Ledger Blue: one action per screen
    "ink": "#0F172A",  # text, dark UI
    "paper": "#F7F7F5",  # surfaces
    "graphite": "#4B5563",  # secondary text
    "hairline": "#E5E7EB",  # borders, rules
    "ember": "#C2410C",  # attention, unposted, overdue
    "verified": "#15803D",  # posted, reconciled
    "flag": "#B91C1C",  # error, locked
}


def read_static(path):
    """Base64 content of a file under afenda_brand/static/, ready for a Binary field."""
    with file_open(f"afenda_brand/static/{path}", "rb") as f:
        return base64.b64encode(f.read())
