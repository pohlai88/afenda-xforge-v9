from odoo import SUPERUSER_ID, api

from odoo.addons.afenda_runtime.mail_templates import strip_invitation_marketing


def migrate(cr, version):
    """Remove the marketing paragraphs from the stored invitation mails.

    The auth_signup templates are noupdate, so an existing database keeps the
    body it was installed with; this runs once, on the upgrade that crosses
    19.0.1.2.0 (odoo/modules/migration.py:209). A fresh install gets the same
    function from `post_init_hook`.
    """
    strip_invitation_marketing(api.Environment(cr, SUPERUSER_ID, {}))
