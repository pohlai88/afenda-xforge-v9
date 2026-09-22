import base64

from odoo.tools import file_open

from .brand import BRAND

_DEFAULT_COMPANY_NAMES = {"My Company", "YourCompany"}

# base ships font="Lato" and leaves the layout and the two report colors empty
# (odoo/addons/base/models/res_company.py:88-91).
_UPSTREAM_REPORT_FONT = "Lato"

# The email colour values AFENDA is entitled to overwrite: upstream's own
# default, and any value an earlier AFENDA release wrote and has since
# superseded. The superseded entries exist because the ordinary "only while it
# is still upstream's" guard cannot see them -- a company holding one is not at
# upstream's default, so the guard would skip it forever and the fix would
# never reach a database that predates it.
#
# Delete a superseded entry once no database installed before its fix remains.
_REPLACEABLE_EMAIL_COLORS = {
    # Upstream defaults: addons/mail/models/res_company.py:28-33.
    "email_primary_color": (
        "#FFFFFF",  # upstream: the button TEXT, which is also our value
        # Superseded (fixed 2026-09-23): the hook had mail's two names
        # inverted and wrote the button FILL colour into the TEXT field.
        BRAND["primary"],
    ),
    "email_secondary_color": (
        "#875A7B",  # upstream: the Odoo purple button FILL
        # Superseded (same inversion): ink landed in the FILL field, so the
        # notification button rendered Ledger Blue on ink -- unreadable.
        BRAND["ink"],
    ),
}


def _is_replaceable(current, replaceable):
    """True while `current` is a value AFENDA may still overwrite."""
    return not current or current.upper() in {value.upper() for value in replaceable}


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

    _apply_company_branding(env)
    refresh_app_icons(env)


def _apply_company_branding(env):
    """Write the AFENDA logo, name, colours, font and report layout on every company.

    Module-level so the 19.0.1.0.1 migration can re-apply it on update: a
    `post_init_hook` runs at install only, so without that call a database
    installed before a branding fix keeps the broken value for good.

    Every field is guarded. A field is written only while it still holds a
    value AFENDA is entitled to replace -- nothing, upstream's default, or (for
    the two email colours) a value an earlier AFENDA release wrote and has
    since superseded. An administrator's own choice is never overwritten,
    neither by a re-install nor by the migration.
    """
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
            if field not in company._fields:
                continue
            current, intended = company[field], BRAND[key]
            if not _is_replaceable(current, _REPLACEABLE_EMAIL_COLORS[field]):
                continue
            if not current or current.upper() != intended.upper():
                vals[field] = intended
        # Printed documents. A document carries no action, so its accents are
        # ink and graphite, not Ledger Blue. Each field is written only while it
        # still holds the upstream default, so neither a re-install nor the
        # migration stomps a font, layout or colour an administrator has since
        # picked. Writing any of them regenerates the
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
    return companies


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
