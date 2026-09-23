# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""Re-read the cached root-menu icons after the reduction fix redrew them.

Two changes since 19.0.1.0.4 rewrote the module icon files on disk, and neither
of them can reach an existing database on its own:

- `marketing_card` and `pos_restaurant` had no entry in `APP_GLYPHS`, so
  `design_for` fell through to the grey AFENDA mark - the placeholder meant for
  technical plumbing, not for two shipping apps. Both now carry a real design.
- Every other icon was redrawn by the reduction fix. The downscale used to run
  on the composited RGBA with LANCZOS, which overshoots a flat fill next to an
  edge and mixes colour out of the transparent ground; the result was that a
  declared colour did not survive to the file. MOSS #4C8A56 was rendering as
  (77,140,87) across 4% of the calendar icon and 6% of project. Reducing in
  mask space fixed it, and 88 files changed.

`web_icon_data` is the apps menu's own copy, taken when `web_icon` was last
written (odoo/addons/base/models/ir_ui_menu.py:155-162, both create and write).
A module update that does not rewrite `web_icon` never recomputes it, so -u
alone leaves the old artwork in place no matter how many times it is run. That
was measured rather than assumed: with the corrected files already on disk, the
cached calendar attachment still carried 398 pixels of (77,140,87) - 3.98% of
its canvas, exactly what `test_app_icons_are_branded` reports - until
`refresh_app_icons` was called, after which the gate went green.

Only the icons. The company branding from 19.0.1.0.1 and the logo, PWA icon and
bot avatar from 19.0.1.0.4 are untouched by this release, and re-running either
here would widen the blast radius of an icon redraw for no reason.

`post-` stage, and an absolute import, for the same reasons as 19.0.1.0.1:
migration scripts are loaded standalone by `load_script`
(odoo/modules/module.py:617-623) and have no package context.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.afenda_brand.hooks import refresh_app_icons


def migrate(cr, version):
    refresh_app_icons(api.Environment(cr, SUPERUSER_ID, {}))
