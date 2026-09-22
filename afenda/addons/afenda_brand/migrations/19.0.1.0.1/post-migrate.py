# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""Re-apply the branding defaults on update, not only on install.

`post_init_hook` runs at install only, so `-u afenda_brand` against an existing
database never refreshed the branding the hook writes. Two fixes were stranded
that way: companies kept `email_secondary_color = #0F172A`, the button FILL
from before mail's text/fill names were un-inverted, so every notification
email shipped an unreadable Ledger-Blue-on-ink button; and they kept
`font = 'Lato'` with no report layout, so the document defaults never applied.

The app icons need the same treatment: `web_icon_data` is a cached copy of the
icon file, refreshed only when `web_icon` is written, so an updated database
keeps whatever artwork was current when its root menus were created.

What this deliberately does NOT re-apply is the company favicon: it is the one
branding field with no "still upstream's" test available, so it is written at
install only and an administrator's upload survives every upgrade.

`post-` stage: this runs after the module's own data is loaded, so
`web.external_layout_standard` and the re-declared `res.company` fields exist.

Migration scripts are loaded standalone by `load_script`
(odoo/modules/module.py:617-623) and have no package context, so the import
below must be absolute; a relative `..hooks` would raise.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.afenda_brand.hooks import _apply_company_branding, refresh_app_icons


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # `replace_superseded` is passed here and nowhere else: repairing a value
    # AFENDA itself wrote and has since superseded is a one-shot job for the
    # databases that predate the fix, not standing behaviour of the hook.
    _apply_company_branding(env, replace_superseded=True)
    refresh_app_icons(env)
