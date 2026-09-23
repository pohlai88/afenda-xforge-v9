# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
{
    "name": "AFENDA xForge Runtime",
    "summary": "Null adapters for the services Odoo hosts: nothing leaves the deployment",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tools",
    "author": "AFENDA",
    "website": "https://www.nexuscanon.com",
    "license": "LGPL-3",
    "application": False,
    "auto_install": False,
    # Installed explicitly by the deploy init, not pulled in by afenda_brand.
    # `iap` owns iap.endpoint and the enrich API; `partner_autocomplete` and
    # `base_import_module` own the methods overridden in models/.
    "depends": [
        "afenda_brand",
        "iap",
        "partner_autocomplete",
        "base_import_module",
    ],
    "data": [
        "data/ir_config_parameter.xml",
    ],
}
