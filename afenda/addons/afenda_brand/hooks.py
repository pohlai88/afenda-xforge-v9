import base64

from odoo.tools import file_open

from .brand import BRAND

_DEFAULT_COMPANY_NAMES = {"My Company", "YourCompany"}


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
    for company in companies:
        vals = {}
        if company.uses_default_logo or not company.logo:
            vals["logo"] = logo
        if company.name in _DEFAULT_COMPANY_NAMES:
            vals["name"] = BRAND["short"]
        for field, key in (
            ("primary_color", "primary"),
            ("secondary_color", "ink"),
            ("email_primary_color", "primary"),
            ("email_secondary_color", "ink"),
        ):
            if field in company._fields:
                vals[field] = BRAND[key]
        if "favicon" in company._fields:
            vals["favicon"] = favicon
        company.write(vals)
