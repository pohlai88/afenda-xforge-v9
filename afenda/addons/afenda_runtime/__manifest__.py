# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
{
    "name": "AFENDA xForge Runtime",
    "summary": "Null adapters for the services Odoo hosts: nothing leaves the deployment",
    # 19.0.1.2.1: /request-access's back link and the controller's unused
    # `product` value; a view and a controller only, no migration. Bumped so
    # `module upgrade --outdated` selects this module on its own, not only
    # when afenda_brand's upgrade happens to pull it in.
    "version": "19.0.1.2.1",
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
    # own install; depending on it makes that data load before ours. It also
    # owns the invitation mails that mail_templates.py edits at install
    # (post_init_hook) and on upgrade (migrations/19.0.1.2.0).
    "depends": [
        "afenda_brand",
        "auth_signup",
        "iap",
        "partner_autocomplete",
        "base_import_module",
    ],
    "post_init_hook": "post_init_hook",
    "data": [
        "data/ir_config_parameter.xml",
        "views/request_access_templates.xml",
    ],
}
