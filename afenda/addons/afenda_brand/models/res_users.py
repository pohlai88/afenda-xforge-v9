from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    # mail_bot's onboarding conversation is written around Odoo: its name, its
    # tour, its links to odoo.com. Keep the bot (channels need an author) but
    # never start the onboarding for anyone.
    odoobot_state = fields.Selection(default="disabled")

    def _rpc_api_keys_only(self):
        """XML-RPC and JSON-RPC accept API keys only, never passwords.

        The mechanism upstream uses for 2FA users, applied to everyone: a
        leaked or guessed password cannot be used against the RPC endpoints,
        and every integration has a revocable, expiring key. Browser login is
        interactive and unaffected.
        """
        return True
