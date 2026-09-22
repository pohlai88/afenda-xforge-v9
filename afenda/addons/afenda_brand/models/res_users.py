from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    # mail_bot's onboarding conversation is written around Odoo: its name, its
    # tour, its links to odoo.com. Keep the bot (channels need an author) but
    # never start the onboarding for anyone.
    odoobot_state = fields.Selection(default="disabled")
