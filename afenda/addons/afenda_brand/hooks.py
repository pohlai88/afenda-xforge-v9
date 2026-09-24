import logging

import psycopg2

from odoo.exceptions import UserError

from .brand import BRAND, read_static

_logger = logging.getLogger(__name__)

_DEFAULT_COMPANY_NAMES = {"My Company", "YourCompany"}

# Odoo S.A. services a self-hosted AFENDA never uses. Each key is read when the
# feature is used, with an odoo.com default, so pointing it at a closed local
# port makes the feature fail fast, including for modules installed later.
# iap_vies.endpoint is left out on purpose: base_vat refuses any value that is
# not an odoo.com URL, which would break VAT editing. The network layer (see
# afenda/SPEC.md) is what actually blocks Odoo S.A.; this is for a clean UX.
ODOO_SA_ENDPOINT_PARAMS = (
    "iap.endpoint",
    "iap.partner_autocomplete.endpoint",
    "sms.endpoint",
    "snailmail.endpoint",
    "enrich.endpoint",
    "reveal.endpoint",
    "html_editor.media_library_endpoint",
    "html_editor.olg_api_endpoint",
    "website.website_api_endpoint",
    "website.olg_api_endpoint",
)
BLACKHOLE_URL = "http://127.0.0.1:9"


def block_odoo_services(env):
    """Enforce the self-hosted policy (SPEC.md §5, decision D1).

    Runs at install and on every registry load, so databases upgraded from an
    older version and modules installed later (base_vat, auth_oauth) are
    covered. It reads first and writes only on drift, so a normal boot does no
    writes. An endpoint key may be pointed at a real service; an empty one is
    reset. The VIES cron and the "Odoo.com Accounts" login are always off.
    """
    icp = env["ir.config_parameter"].sudo()
    missing = [key for key in ODOO_SA_ENDPOINT_PARAMS if not icp.get_param(key)]
    cron = env.ref("base_vat.vies_iap_check_update", raise_if_not_found=False)
    provider = env.ref("auth_oauth.provider_openerp", raise_if_not_found=False)
    if not (missing or (cron and cron.active) or (provider and provider.enabled)):
        return
    # After an upgrade every worker loads the registry at once, and ir.cron
    # refuses writes while the job runs: never break the boot, retry next time.
    try:
        with env.cr.savepoint():
            for key in missing:
                icp.set_param(key, BLACKHOLE_URL)
            if cron and cron.active:
                cron.sudo().active = False
            if provider and provider.enabled:
                provider.sudo().enabled = False
    except (UserError, psycopg2.Error) as e:
        _logger.info("Odoo S.A. services not switched off yet, retrying on the next start: %s", e)


def rebrand_welcome_post(env):
    """Rename the "Welcome to Odoo!" post in #general.

    Edited rather than deleted: the record is noupdate, so the edit survives
    `-u mail`, whereas a deleted one would be recreated.
    """
    welcome = env.ref("mail.module_install_notification", raise_if_not_found=False)
    if welcome and "odoo" in (welcome.subject or "").lower():
        welcome.sudo().subject = f"Welcome to {BRAND['product']}!"


def email_colors():
    """mail's email_primary_color is the button text, email_secondary_color the button."""
    return {"email_primary_color": "#FFFFFF", "email_secondary_color": BRAND["primary"]}


def post_init_hook(env):
    """Apply the AFENDA identity to the database once, at install time.

    Everything here is a plain record write, so an administrator can still
    change any of it later from Settings.
    """
    env["ir.config_parameter"].sudo().set_param("web.web_app_name", BRAND["product"])
    block_odoo_services(env)

    # web_pwa_customize stores the PWA name, colors and resized icons through
    # its settings model, exactly as if saved from the Settings screen.
    icon = read_static("img/icon-512.png")
    env["res.config.settings"].sudo().create(
        {
            "pwa_short_name": BRAND["short"],
            "pwa_theme_color": BRAND["primary"],
            "pwa_background_color": BRAND["paper"],
            "pwa_icon": icon,
        },
    ).execute()

    # The system bot: AFENDA's name and mark, and no Odoo onboarding chat.
    bot = env.ref("base.partner_root").sudo()
    bot.write({"name": BRAND["bot"], "image_1920": icon})
    users = env["res.users"].sudo().with_context(active_test=False).search([])
    users.write({"odoobot_state": "disabled"})
    bot_channels = env["discuss.channel"].sudo().search(
        [("channel_type", "=", "chat"), ("channel_member_ids.partner_id", "=", bot.id)],
    )
    env["mail.message"].sudo().search(
        [
            ("model", "=", "discuss.channel"),
            ("res_id", "in", bot_channels.ids),
            ("author_id", "=", bot.id),
        ],
    ).unlink()
    rebrand_welcome_post(env)

    logo = read_static("img/logo.png")
    favicon = read_static("img/favicon.ico")
    for company in env["res.company"].sudo().search([]):
        vals = {
            "primary_color": BRAND["primary"],
            "secondary_color": BRAND["ink"],
            "favicon": favicon,
            **email_colors(),
        }
        if company.uses_default_logo or not company.logo:
            vals["logo"] = logo
        if company.name in _DEFAULT_COMPANY_NAMES:
            vals["name"] = BRAND["short"]
        company.write(vals)
