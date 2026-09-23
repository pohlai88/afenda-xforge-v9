import base64
import hashlib

from odoo.tools import file_open

from .brand import BRAND

_DEFAULT_COMPANY_NAMES = {"My Company", "YourCompany"}

# base ships font="Lato" and leaves the layout and the two report colors empty
# (odoo/addons/base/models/res_company.py:88-91).
_UPSTREAM_REPORT_FONT = "Lato"

# Upstream's own defaults for the two email colours
# (addons/mail/models/res_company.py:28-33). A company still holding one of
# these has never been branded, so writing over it takes nothing away.
_UPSTREAM_EMAIL_COLORS = {
    "email_primary_color": ("#FFFFFF",),  # the button TEXT
    "email_secondary_color": ("#875A7B",),  # the Odoo purple button FILL
}

# Values an earlier AFENDA release wrote and has since superseded. A company
# holding one is not at upstream's default, so the guard above cannot see it
# and the fix would never reach a database that predates it.
#
# Only migrations/19.0.1.0.1/post-migrate.py opts in, through
# `replace_superseded=True`. That is deliberate: the repair has to reach each
# stale database exactly once, and keeping it off every other code path keeps
# the one risk it carries -- an administrator who genuinely picked the
# superseded colour -- out of the install hook and out of any future caller.
# This table is therefore migration-local in practice, and goes with that
# migration once no database installed before 2026-09-23 remains.
_SUPERSEDED_EMAIL_COLORS = {
    # The inversion fixed on 2026-09-23: the hook had mail's two names the
    # wrong way round, so the button FILL colour landed in the TEXT field...
    "email_primary_color": (BRAND["primary"],),
    # ...and ink landed in the FILL field, which rendered the notification
    # button Ledger Blue on ink -- unreadable.
    "email_secondary_color": (BRAND["ink"],),
}

# sha256 of every company logo AFENDA has shipped before this release, over the
# raw bytes of static/img/logo.png as it stood then. A company holding one of
# these holds AFENDA's own superseded artwork, not an administrator's upload, so
# the logo may be replaced.
#
# Why a hash table and not `uses_default_logo`: that field is a *stored* compute
# (odoo/addons/base/models/res_company.py:175-178) comparing the stored logo
# against `_get_logo()`, which afenda_brand points at static/img/logo.png
# (models/res_company.py:46-48). It depends on `partner_id.image_1920`, so
# redrawing that file does not recompute it -- but the first unrelated write to
# the partner image does, and then the stored old logo no longer equals the new
# default, the flag latches False, and the guard below reads AFENDA's own
# artwork as an administrator's choice and refuses to replace it for good.
# Hashing the artwork we shipped is the only test that survives that latch.
#
# Migration-local in practice, exactly like _SUPERSEDED_EMAIL_COLORS: only
# migrations/19.0.1.0.3/post-migrate.py opts in. Append a line whenever
# static/img/logo.png is redrawn; drop older entries once no database predating
# them remains.
_SUPERSEDED_LOGO_SHA256 = (
    # 19.0.1.0.0 - 19.0.1.0.2: the lockup before the Engineered X mark.
    "1fe623124978f0fe22cbe4de8642e71fafb1cb9b4ce367de96d37cfd24aeceb6",
)

# Same idea for the two places icon-512.png is copied into the database.
_SUPERSEDED_ICON_SHA256 = (
    # 19.0.1.0.0 - 19.0.1.0.2: the tile before the Engineered X mark.
    "587e3a117db7cedc01cb0c5d91c26c0e6b4da8299d8ab0eba78dc6a4063e5cae",
)


def _is_replaceable(current, replaceable):
    """True while `current` is a value AFENDA may still overwrite."""
    return not current or current.upper() in {value.upper() for value in replaceable}


def _is_superseded_image(current, digests):
    """True when `current` (base64) is AFENDA artwork from an earlier release.

    Anything unreadable counts as not ours, so a corrupt or foreign value is
    left alone rather than overwritten.
    """
    if not current:
        return False
    try:
        raw = base64.b64decode(current)
    except (TypeError, ValueError):
        return False
    return hashlib.sha256(raw).hexdigest() in digests


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

    companies = _apply_company_branding(env)
    # The favicon stays here, outside `_apply_company_branding`, because it is
    # the one branding field with no guard available: web_favicon's default is
    # Odoo's own icon with a randomly coloured bottom row
    # (afenda/oca/web/web_favicon/models/res_company.py:21-50), so a stored
    # value cannot be told apart from one an administrator uploaded. Writing it
    # at install only keeps that blast radius exactly where it has always been;
    # the migration must not re-run it on a configured database.
    if "favicon" in companies._fields:
        companies.write({"favicon": _read_static("img/favicon.ico")})

    refresh_app_icons(env)


def _apply_company_branding(env, replace_superseded=False):
    """Write the AFENDA logo, name, colours, font and report layout on every company.

    Module-level so the 19.0.1.0.1 migration can re-apply it on update: a
    `post_init_hook` runs at install only, so without that call a database
    installed before a branding fix keeps the broken value for good.

    Every field written here is guarded on its value still being upstream's own
    default (or nothing at all), so an administrator's name, logo, font, layout
    or colour is never overwritten, neither by a re-install nor by the
    migration. `replace_superseded` widens that test for the two email colours
    and the logo, to also accept a value an earlier AFENDA release wrote and has
    since superseded; see `_SUPERSEDED_EMAIL_COLORS` and
    `_SUPERSEDED_LOGO_SHA256` for why only the migration passes it.

    The favicon is deliberately not written here; see `post_init_hook`.
    """
    # sudo(): branding has to reach every company, not only the ones the
    # installing user is allowed into (res.company is filtered by `company_ids`).
    companies = env["res.company"].sudo().search([])
    logo = _read_static("img/logo.png")
    # The standard layout: one column of figures, no boxes, no filled headers.
    report_layout = env.ref("web.external_layout_standard", raise_if_not_found=False)
    for company in companies:
        vals = {}
        # `uses_default_logo` compares against the logo file as it stands now,
        # so it stops recognising artwork we shipped earlier; see
        # _SUPERSEDED_LOGO_SHA256 for why the migration needs the hash test too.
        if (
            company.uses_default_logo
            or not company.logo
            or (
                replace_superseded
                and _is_superseded_image(company.logo, _SUPERSEDED_LOGO_SHA256)
            )
        ):
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
            replaceable = _UPSTREAM_EMAIL_COLORS.get(field, ())
            if replace_superseded:
                replaceable += _SUPERSEDED_EMAIL_COLORS.get(field, ())
            current, intended = (company[field] or "").upper(), BRAND[key]
            if current != intended.upper() and _is_replaceable(current, replaceable):
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


def refresh_cached_brand_images(env):
    """Re-read the two database copies of icon-512.png from the file on disk.

    Both are copies taken at install time, not references, so redrawing the file
    leaves them behind:

    - the PWA icon, stored by web_pwa_customize as an `ir.attachment` at
      /web_pwa_customize/icon.<ext> plus one resized attachment per size
      (afenda/oca/web/web_pwa_customize/models/res_config_settings.py:29-70);
    - the system bot's avatar, `res.partner.image_1920` on `base.partner_root`,
      written by `post_init_hook`.

    Update-only, and guarded: each is rewritten only while it still holds
    artwork AFENDA itself shipped (`_SUPERSEDED_ICON_SHA256`), so an
    administrator's own upload survives. `post_init_hook` deliberately does not
    call this -- at install there is nothing of ours to recognise yet, and the
    bot still holds Odoo's avatar, which install is meant to replace outright.

    Returns the names of what it rewrote, for the migration to log.
    """
    written = []
    icon = _read_static("img/icon-512.png")

    # The settings model is the only safe writer for the PWA icon: writing the
    # attachment directly would leave the resized copies stale. `create` fills
    # every other field from `get_values`, so `execute` writes back the
    # administrator's current PWA name and colours unchanged.
    settings = env["res.config.settings"].sudo()
    stored = env["ir.attachment"].sudo().search(
        [("url", "=like", settings._pwa_icon_url_base + ".%")], limit=1
    )
    if not stored or _is_superseded_image(stored.datas, _SUPERSEDED_ICON_SHA256):
        settings.create({"pwa_icon": icon}).execute()
        written.append("pwa_icon")

    bot = env.ref("base.partner_root", raise_if_not_found=False)
    if bot and _is_superseded_image(bot.sudo().image_1920, _SUPERSEDED_ICON_SHA256):
        bot.sudo().image_1920 = icon
        written.append("partner_root.image_1920")

    return written
