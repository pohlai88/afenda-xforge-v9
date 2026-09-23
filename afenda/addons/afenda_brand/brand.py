"""Single source of truth for the AFENDA xForge identity (v2.1, 2026-09-22).

Keys: product, short, bot, domain, docs_path, url_prefix, tagline, and the
colors primary, on_primary, ink, paper, graphite, hairline, ember, verified,
flag, favorite, the tags palette, and the dark sub-dict.

Keep in sync with static/src/scss/primary_variables.scss.
"""

BRAND = {
    "product": "AFENDA xForge",
    "short": "AFENDA",
    "bot": "AFENDA Bot",
    "domain": "nexuscanon.com",
    "docs_path": "/docs/",  # generated documentation, served same-origin (phase 3)
    "url_prefix": "app",  # browser address prefix, replaces "odoo"
    "tagline": "The truth of your business, kept.",
    # Colors
    "primary": "#1E3A8A",  # Ledger Blue: one action per screen
    "on_primary": "#FFFFFF",  # text and icons drawn on primary
    "ink": "#0F172A",  # text, dark UI
    "paper": "#F7F7F5",  # surfaces
    "graphite": "#4B5563",  # secondary text
    "hairline": "#E5E7EB",  # borders, rules
    "ember": "#C2410C",  # attention, unposted, overdue
    "verified": "#15803D",  # posted, reconciled
    "flag": "#B91C1C",  # error, locked
    "favorite": "#A16207",  # starred records
    # Tag / kanban palette, mirrors $o-colors in primary_variables.scss.
    "tags": [
        "#9CA3AF", "#A33A3A", "#B5651D", "#A16207", "#3B6EA8", "#7C4F7F",
        "#9A6B4F", "#2F8F8A", "#3448A8", "#A8447A", "#4C8A56", "#6B5FA8",
    ],
    # Dark color scheme, mirrors static/src/scss/primary_variables.dark.scss.
    "dark": {
        "background": "#0B1120",  # behind the views
        "view": "#111827",  # the views themselves
        "text": "#E5E7EB",
        "primary": "#3B5BDB",  # Ledger Blue lifted to carry on ink
        "link": "#A5B4FC",
        "border": "#1F2937",
        "navbar": "#0B1120",
    },
}
