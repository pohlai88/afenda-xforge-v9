"""Single source of truth for the AFENDA xForge identity (v2.1, 2026-09-22).

Keys: product, short, bot, domain, docs_path, url_prefix, tagline, and the
colors primary, on_primary, ink, paper, graphite, hairline, ember, verified,
flag, favorite, the tags palette, the neutral ramp, and the dark sub-dict
(which carries the dark ramp).

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
        # The selected/active ground. Upstream mixes the action into
        # $o-gray-100 (web/static/src/scss/primary_variables.scss:133), which in
        # the inverted ramp is the darkest thing on screen -- selection would be
        # invisible. Named here so the dark scheme invents no colour of its own:
        # every hex in primary_variables.dark.scss mirrors a value from this
        # dict, which test_the_token_files_invent_no_colour enforces.
        "selection": "#1E2A4A",
    },
}

# Neutral ramp, one family in nine steps, mirroring $o-gray-100..900 in
# static/src/scss/primary_variables.scss. Three of its steps are brand values
# this dict already names, so they are read back from it rather than typed a
# second time: a change to hairline, graphite or ink moves the ramp with it.
BRAND["ramp"] = (
    "#F9FAFB",  # 100
    "#F3F4F6",  # 200
    BRAND["hairline"],  # 300: the rule
    "#D1D5DB",  # 400
    "#9CA3AF",  # 500
    "#6B7280",  # 600
    BRAND["graphite"],  # 700: secondary text
    "#374151",  # 800
    BRAND["ink"],  # 900: body text
)

# The same family walked the other way, mirroring
# static/src/scss/primary_variables.dark.scss. Derived rather than restated, so
# "same family, same number of steps, opposite direction" is a property of this
# file instead of a claim in a comment: the dark scheme's own three anchors take
# 100-300, the middle of the light ramp reverses into 400-800, and 900 is the
# light ramp's 200 -- the one step light enough to caption the fills above it.
BRAND["dark"]["ramp"] = (
    BRAND["dark"]["background"],  # 100: the ground
    BRAND["dark"]["view"],  # 200: the view
    BRAND["dark"]["border"],  # 300: the rule
    *reversed(BRAND["ramp"][3:8]),  # 400-800: #374151 .. #D1D5DB
    BRAND["ramp"][1],  # 900: what sits on the fills above
)
