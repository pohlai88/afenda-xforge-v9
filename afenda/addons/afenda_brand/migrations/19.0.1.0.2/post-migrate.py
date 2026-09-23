# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""Re-read the cached root-menu icons after the app icons were redrawn.

The module icons are no longer a Ledger Blue tile with a white glyph; they are
free-standing duotone marks. That is a change to files on disk, and files on
disk are not what the apps menu draws: it draws `web_icon_data`, a copy of the
icon file taken when `web_icon` was last written
(odoo/addons/base/models/ir_ui_menu.py:158-162). A database created before this
release therefore keeps the old tiles in its apps menu forever unless something
writes `web_icon` back, which is all `refresh_app_icons` does.

Only the icons: the company branding re-applied by the 19.0.1.0.1 migration is
unchanged by this release, and re-running it here would widen the blast radius
of an icon redraw to every company's logo, colours and report layout for no
reason.

`post-` stage, and an absolute import, for the same reasons as 19.0.1.0.1:
migration scripts are loaded standalone by `load_script`
(odoo/modules/module.py:617-623) and have no package context.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.afenda_brand.hooks import refresh_app_icons


def migrate(cr, version):
    refresh_app_icons(api.Environment(cr, SUPERUSER_ID, {}))
