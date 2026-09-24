import logging

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
    """Switch off what a later install or upgrade of base_vat or auth_oauth brings back.

    Called on every registry load, so it reads first and writes only on drift:
    a normal boot does no writes.
    """
    cron = env.ref("base_vat.vies_iap_check_update", raise_if_not_found=False)
    if cron and cron.active:
        try:
            with env.cr.savepoint():
                cron.sudo().active = False
        except UserError:
            _logger.info("VIES cron is running; it will be disabled on the next start")
    provider = env.ref("auth_oauth.provider_openerp", raise_if_not_found=False)
    if provider and provider.enabled:
        provider.sudo().enabled = False


def post_init_hook(env):
    """Apply the AFENDA identity to the database once, at install time.

    Everything here is a plain record write, so an administrator can still
    change any of it later from Settings.
    """
    icp = env["ir.config_parameter"].sudo()
    icp.set_param("web.web_app_name", BRAND["product"])
    for key in ODOO_SA_ENDPOINT_PARAMS:
        if not icp.get_param(key):
            icp.set_param(key, BLACKHOLE_URL)
    block_odoo_services(env)

    # web_pwa_customize stores the PWA name, colors and resized icons through
    # its settings model, exactly as if saved from the Settings screen.
    env["res.config.settings"].sudo().create(
        {
            "pwa_short_name": BRAND["short"],
            "pwa_theme_color": BRAND["primary"],
            "pwa_background_color": BRAND["paper"],
            "pwa_icon": read_static("img/icon-512.png"),
        },
    ).execute()

    # The system bot: AFENDA's name and mark, and no Odoo onboarding chat.
    bot = env.ref("base.partner_root").sudo()
    bot.write({"name": BRAND["bot"], "image_1920": read_static("img/icon-512.png")})
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
    # The "Welcome to Odoo!" post in #general.
    welcome = env.ref("mail.module_install_notification", raise_if_not_found=False)
    if welcome:
        welcome.sudo().unlink()

    logo = read_static("img/logo.png")
    favicon = read_static("img/favicon.ico")
    for company in env["res.company"].sudo().search([]):
        vals = {
            "primary_color": BRAND["primary"],
            "secondary_color": BRAND["ink"],
            "email_primary_color": BRAND["primary"],
            "email_secondary_color": BRAND["ink"],
            "favicon": favicon,
        }
        if company.uses_default_logo or not company.logo:
            vals["logo"] = logo
        if company.name in _DEFAULT_COMPANY_NAMES:
            vals["name"] = BRAND["short"]
        company.write(vals)
