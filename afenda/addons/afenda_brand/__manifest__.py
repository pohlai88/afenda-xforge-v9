# Part of AFENDA xForge. See LICENSE file for full copyright and licensing details.
{
    "name": "AFENDA xForge Branding",
    "summary": "Brand the web client, login, emails and portal as AFENDA xForge",
    # 19.0.1.0.1 carries migrations/19.0.1.0.1/post-migrate.py, which re-applies
    # the company branding on update: post_init_hook runs at install only.
    # 19.0.1.0.2 re-reads the cached root-menu icons: the app icons were redrawn
    # as free-standing duotone marks, and `web_icon_data` is a copy taken when
    # `web_icon` was last written, so a database that skipped it keeps the old
    # tiles in the apps menu no matter what is on disk.
    "version": "19.0.1.0.2",
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
        # OCA/server-brand 19.0
        # `mail_debranding` is deliberately absent: it only acts on a body that
        # still contains an `<a href>` to odoo.com (mail_render_mixin.py:28-32),
        # and the rebrand rewrote every such href, so it is a no-op on this
        # tree. `portal_debranding` is absent for a harder reason: its login
        # xpath anchors on that same rewritten href
        # (views/web_login_debrand.xml:5-9) and would raise on install.
        # See afenda/README.md for the audit.
        "disable_odoo_online",
        "remove_odoo_enterprise",
        # OCA/web 19.0
        "web_favicon",
        "web_pwa_customize",
        "web_no_bubble",
    ],
    "data": [
        "views/webclient_templates.xml",
        "views/mail_templates.xml",
        "views/docs_placeholder.xml",
    ],
    "assets": {
        "web._assets_primary_variables": [
            ("prepend", "afenda_brand/static/src/scss/primary_variables.scss"),
        ],
        "web.assets_web_dark": [
            (
                "before",
                "afenda_brand/static/src/scss/primary_variables.scss",
                "afenda_brand/static/src/scss/primary_variables.dark.scss",
            ),
        ],
        "web.assets_backend": [
            "afenda_brand/static/src/scss/fonts.scss",
            "afenda_brand/static/src/scss/backend.scss",
            "afenda_brand/static/src/js/title_service.js",
            "afenda_brand/static/src/js/effects.js",
            "afenda_brand/static/src/js/user_menu.js",
            "afenda_brand/static/src/xml/res_config_edition.xml",
            "afenda_brand/static/src/xml/error_dialogs.xml",
        ],
        "web.assets_frontend": [
            "afenda_brand/static/src/scss/fonts.scss",
            "afenda_brand/static/src/scss/login.scss",
        ],
        # Printed documents: static font instances (wkhtmltopdf cannot use the
        # variable fonts) plus the document rules.
        "web.report_assets_common": [
            "afenda_brand/static/src/scss/fonts_report.scss",
            "afenda_brand/static/src/scss/report.scss",
        ],
    },
    "post_init_hook": "post_init_hook",
}
