# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
"""Re-read the company logo, the PWA icon and the bot avatar after the redraw.

19.0.1.0.2 and 19.0.1.0.3 each refreshed the root-menu icons, which are one of
four database copies of the brand artwork. This release covers the other three,
which no migration has ever touched:

- every company's logo, a copy of img/logo.png;
- the PWA icon, stored by web_pwa_customize as an `ir.attachment` at
  /web_pwa_customize/icon.<ext> plus one resized attachment per size;
- the system bot's avatar, `image_1920` on `base.partner_root`.

`refresh_app_icons` is deliberately NOT called here: 19.0.1.0.3 already did it
for the V2 redraw, and a database below that version runs that script before this
one, so the menus are fresh by the time we get here.

The logo is the one that cannot be fixed by re-running the install hook's guard.
`_apply_company_branding` writes it only while `uses_default_logo` is true, and
that field is a stored compute comparing the stored logo against img/logo.png as
it stands *now* (odoo/addons/base/models/res_company.py:175-178). Once it
recomputes after a redraw, the artwork we shipped earlier stops matching, the
flag latches false, and the logo is frozen as though an administrator had
uploaded it -- so no later `-u` can ever repair it. `replace_superseded=True`
adds the hash test that still recognises our own previous artwork; see
`_SUPERSEDED_LOGO_SHA256`.

Deliberately not re-applied: the company favicon, for the reason given in
19.0.1.0.1 -- web_favicon's default is randomised per company, so a stored value
cannot be told apart from an administrator's upload.

`post-` stage, and an absolute import, for the same reasons as 19.0.1.0.1
through 19.0.1.0.3: migration scripts are loaded standalone by `load_script`
(odoo/modules/module.py:617-623) and have no package context.
"""
import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.afenda_brand.hooks import (
    _apply_company_branding,
    refresh_cached_brand_images,
)

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    companies = _apply_company_branding(env, replace_superseded=True)
    cached = refresh_cached_brand_images(env)
    _logger.info(
        "afenda_brand 19.0.1.0.4: re-read branding on %d companies, rewrote %s",
        len(companies),
        ", ".join(cached) or "no cached images",
    )
