# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
{
    "name": "AFENDA xForge Branding",
    "summary": "Brand the web client, login, emails and portal as AFENDA xForge",
    "version": "19.0.1.2.0",
    "category": "Hidden/Tools",
    "author": "AFENDA",
    "website": "https://afenda.app",
    "license": "LGPL-3",
    "application": False,
    "auto_install": False,
    "depends": [
        "web",
        "base_setup",
        "mail",
        "mail_bot",
        "portal",
        "api_doc",
        # OCA/server-brand 19.0
        "disable_odoo_online",
        "remove_odoo_enterprise",
        "mail_debranding",
        "portal_debranding",
        # OCA/web 19.0
        "web_favicon",
        "web_pwa_customize",
        "web_no_bubble",
    ],
    "data": [
        "views/webclient_templates.xml",
    ],
    "assets": {
        "web._assets_primary_variables": [
            ("prepend", "afenda_brand/static/src/scss/primary_variables.scss"),
        ],
        "web.assets_backend": [
            "afenda_brand/static/src/scss/fonts.scss",
            "afenda_brand/static/src/scss/backend.scss",
            "afenda_brand/static/src/js/title_service.js",
            "afenda_brand/static/src/xml/res_config_edition.xml",
        ],
        "web.assets_frontend": [
            "afenda_brand/static/src/scss/fonts.scss",
        ],
        # The /doc API explorer has its own bundle, without the web client's
        # SCSS variables.
        "api_doc.assets": [
            "afenda_brand/static/src/scss/fonts.scss",
            "afenda_brand/static/src/api_doc/api_doc.scss",
            "afenda_brand/static/src/api_doc/api_doc.xml",
        ],
    },
    "post_init_hook": "post_init_hook",
}
