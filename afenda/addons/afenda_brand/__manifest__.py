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
    # 19.0.1.0.6 carries the auth surface, the shell theming and the mail
    # header. It ships no migration and needs none -- views and SCSS reload on
    # upgrade. The bump is not ceremony: deploy/init.sh upgrades with
    # `module upgrade --outdated`, which selects modules by comparing manifest
    # version to installed version, so without it none of this reaches a
    # deployed database. Declared in _VERSIONS_WITHOUT_MIGRATION.
    # 19.0.1.0.7: the auth back links stop carrying reset/signup tokens, back
    # before the action in the tab order, icons hidden from assistive tech.
    # Views and SCSS only, no migration.
    "version": "19.0.1.0.7",
    "category": "Hidden/Tools",
    "author": "AFENDA",
    "website": "https://www.nexuscanon.com",
    "license": "LGPL-3",
    "application": False,
    "auto_install": False,
    "depends": [
        "web",
        "base_setup",
        "mail",
        "mail_bot",
        "portal",
        # Declared because views/webclient_templates.xml inherits their
        # templates (auth_signup.signup, auth_signup.reset_password,
        # auth_totp.auth_totp_form), and an inherit_id needs its parent loaded
        # first. auth_signup already arrives through portal, but only
        # transitively; auth_totp is otherwise only auto-installed and not in
        # this module's graph at all, so its view could load after ours.
        # Upgrading installs a newly declared dependency that is still
        # uninstalled (odoo/addons/base/models/ir_module.py:739-749).
        "auth_signup",
        "auth_totp",
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
        # Before webclient_templates.xml: login_layout t-calls
        # afenda_brand.auth_bear, the inline crystal bear that
        # afenda/tools/crystal_bear generates.
        "views/auth_bear.xml",
        "views/webclient_templates.xml",
        "views/mail_templates.xml",
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
            # Plain .css, not .scss: the bundle concatenates it with only a
            # comment strip and a whitespace collapse
            # (odoo/addons/base/models/assetsbundle.py:965-972), so oklch() and
            # color-mix() reach the browser untouched. The generated scales
            # first, then the skins and states that read them.
            "afenda_brand/static/src/css/auth_bear_scales.css",
            "afenda_brand/static/src/css/auth_bear.css",
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
