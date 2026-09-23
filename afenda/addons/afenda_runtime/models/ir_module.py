from odoo import api, models
from odoo.exceptions import AccessDenied, UserError


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    # Null adapters for the Odoo apps store that base_import_module queries for
    # industry modules (addons/base_import_module/models/ir_module.py:440-563).

    @api.model
    def _get_modules_from_apps(self, fields, module_type, module_name, domain=None, limit=None, offset=None):
        return []

    # Upstream also wraps this in `@ormcache()`; a constant needs no cache.
    @api.model
    def _get_industry_categories_from_apps(self):
        return []

    def button_immediate_install_app(self):
        # Same access gate as upstream, so a non-admin still gets AccessDenied.
        if not self.env.is_admin():
            raise AccessDenied()
        raise UserError(self.env._("Industry packages are not available in this deployment."))
