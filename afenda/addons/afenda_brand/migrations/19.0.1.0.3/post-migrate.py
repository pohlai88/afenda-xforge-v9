# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""Re-read the cached root-menu icons after the V2 duotone redraw.

Same reason as 19.0.1.0.2, a release later: every app icon changed again. The
glyph is now 84% of the short side rather than 88%, and the colour where the
glyph and the accent cross is no longer their raw RGB multiply - eighteen of the
twenty-one brand pairs multiplied to a near-black that read as a hole punched in
the mark, so the crossing is now eased back toward the midpoint until it clears a
luminance floor (`afenda.tools.app_icons.controlled_overlap_colour`).

None of that reaches the apps menu on its own. The menu draws `web_icon_data`, a
copy of the icon file taken when `web_icon` was last written
(odoo/addons/base/models/ir_ui_menu.py:158-162), so a database created before
this release keeps the V1 artwork forever unless something writes `web_icon`
back - which is all `refresh_app_icons` does.

Only the icons, for the same reason as 19.0.1.0.2: the company branding applied
by 19.0.1.0.1 is untouched by this release.

`post-` stage, and an absolute import, because migration scripts are loaded
standalone by `load_script` (odoo/modules/module.py:617-623) and have no package
context.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.afenda_brand.hooks import refresh_app_icons


def migrate(cr, version):
    refresh_app_icons(api.Environment(cr, SUPERUSER_ID, {}))
