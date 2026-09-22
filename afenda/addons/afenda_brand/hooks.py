import base64

from odoo.tools import file_open

from .brand import BRAND

_DEFAULT_COMPANY_NAMES = {"My Company", "YourCompany"}

# base ships font="Lato" and leaves the layout and the two report colors empty
# (odoo/addons/base/models/res_company.py:88-91).
_UPSTREAM_REPORT_FONT = "Lato"


def _read_static(path):
    with file_open(f"afenda_brand/static/{path}", "rb") as f:
        return base64.b64encode(f.read())


def post_init_hook(env):
    """Apply the AFENDA identity to the database once, at install time.

    Everything here is a plain record write, so an administrator can still
    change any of it later from Settings.
    """
    env["ir.config_parameter"].sudo().set_param("web.web_app_name", BRAND["product"])

    # web_pwa_customize stores the PWA name, colors and resized icons through
    # its settings model, exactly as if saved from the Settings screen.
    env["res.config.settings"].sudo().create(
        {
            "pwa_short_name": BRAND["short"],
            "pwa_theme_color": BRAND["primary"],
            "pwa_background_color": BRAND["paper"],
            "pwa_icon": _read_static("img/icon-512.png"),
        }
    ).execute()

    # The system bot: AFENDA's name and mark, and no Odoo onboarding chat.
    bot = env.ref("base.partner_root").sudo()
    bot.write({"name": BRAND["bot"], "image_1920": _read_static("img/icon-512.png")})
    users = env["res.users"].sudo().with_context(active_test=False).search([])
    users.write({"odoobot_state": "disabled"})
    bot_channels = env["discuss.channel"].sudo().search(
        [("channel_type", "=", "chat"), ("channel_member_ids.partner_id", "=", bot.id)]
    )
    env["mail.message"].sudo().search(
        [
            ("model", "=", "discuss.channel"),
            ("res_id", "in", bot_channels.ids),
            ("author_id", "=", bot.id),
        ]
    ).unlink()

    companies = env["res.company"].sudo().search([])
    logo = _read_static("img/logo.png")
    favicon = _read_static("img/favicon.ico")
    # The standard layout: one column of figures, no boxes, no filled headers.
    report_layout = env.ref("web.external_layout_standard", raise_if_not_found=False)
    for company in companies:
        vals = {}
        if company.uses_default_logo or not company.logo:
            vals["logo"] = logo
        if company.name in _DEFAULT_COMPANY_NAMES:
            vals["name"] = BRAND["short"]
        for field, key in (
            # mail names these from the reader's point of view: "primary" is the
            # button TEXT, "secondary" is the button FILL.
            ("email_primary_color", "on_primary"),
            ("email_secondary_color", "primary"),
        ):
            if field in company._fields:
                vals[field] = BRAND[key]
        # Printed documents. A document carries no action, so its accents are
        # ink and graphite, not Ledger Blue. Each field is written only while it
        # still holds the upstream default, so re-installing the module never
        # stomps a font, layout or colour an administrator has since picked.
        # (This hook runs at install only -- `-u afenda_brand` does not call it
        # at all -- so it is a re-install, not an update, that the guards
        # protect against.) Writing any of them regenerates the
        # web.asset_styles_company_report attachment
        # (addons/web/models/models.py:2241-2266).
        # A company created before `font` had a default holds NULL, which is
        # just as unset as Lato.
        if company.font in (False, _UPSTREAM_REPORT_FONT):
            vals["font"] = "Source_Sans_3"
        if report_layout and not company.external_report_layout_id:
            vals["external_report_layout_id"] = report_layout.id
        if not company.primary_color:
            vals["primary_color"] = BRAND["ink"]
        if not company.secondary_color:
            vals["secondary_color"] = BRAND["graphite"]
        if "favicon" in company._fields:
            vals["favicon"] = favicon
        company.write(vals)

    refresh_app_icons(env)


def refresh_app_icons(env):
    """Recompute every root menu's cached icon from the files on disk.

    `web_icon_data` is only recomputed when `web_icon` is written
    (odoo/addons/base/models/ir_ui_menu.py:158-162), and it is what the apps
    menu actually renders (`load_menus`, same file, :262-292). Re-rendering the
    tiles on disk does not touch it, so a database keeps whatever artwork was
    current when its menus were created. Writing each menu's own value back
    re-reads the file.

    Module-level so that an upgrade path can call it without re-running the
    whole install hook.
    """
    roots = (
        env["ir.ui.menu"]
        .sudo()
        .with_context(active_test=False)
        .search([("parent_id", "=", False), ("web_icon", "!=", False)])
    )
    for menu in roots:
        menu.web_icon = menu.web_icon
    return roots
