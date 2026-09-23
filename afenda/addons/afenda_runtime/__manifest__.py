# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
{
    "name": "AFENDA xForge Runtime",
    "summary": "Null adapters for the services Odoo hosts: nothing leaves the deployment",
    "version": "19.0.1.1.0",
    "category": "Hidden/Tools",
    "author": "AFENDA",
    "website": "https://www.nexuscanon.com",
    "license": "LGPL-3",
    "application": False,
    "auto_install": False,
    # Installed explicitly by the deploy init, not pulled in by afenda_brand.
    # `iap` owns iap.endpoint and the enrich API; `partner_autocomplete` and
    # `base_import_module` own the methods overridden in models/.
    # `auth_signup` owns auth_signup.invitation_scope and sets it to b2c at its
    # own install; depending on it makes that data load before ours.
    "depends": [
        "afenda_brand",
        "auth_signup",
        "iap",
        "partner_autocomplete",
        "base_import_module",
    ],
    "data": [
        "data/ir_config_parameter.xml",
        "views/request_access_templates.xml",
    ],
}
