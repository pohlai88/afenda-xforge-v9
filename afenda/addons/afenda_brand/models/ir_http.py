from odoo import models

from ..brand import BRAND


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        """Publish the documentation url to the web client.

        `static/src/js/user_menu.js` reads it for the Help entry; putting it
        here keeps brand.py the single source of truth instead of repeating
        the path in JavaScript.
        """
        info = super().session_info()
        info["afenda_docs_url"] = BRAND["docs_path"]
        return info
