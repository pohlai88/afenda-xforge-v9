from odoo import SUPERUSER_ID, api

from odoo.addons.afenda_brand.brand import BRAND
from odoo.addons.afenda_brand.hooks import (
    block_odoo_services,
    email_colors,
    rebrand_welcome_post,
)


def migrate(cr, version):
    """Bring databases installed at 19.0.1.0.0 to what a fresh install sets."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    # 19.0.1.0.0 swapped the email colors: blue text on an ink button.
    env["res.company"].search([("email_primary_color", "=ilike", BRAND["primary"])]).write(email_colors())
    rebrand_welcome_post(env)
    block_odoo_services(env)
