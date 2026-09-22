import { _t } from "@web/core/l10n/translation";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

/**
 * "Help" in the user menu, pointing at AFENDA's own documentation.
 *
 * Sequence 20 is the slot upstream's "support" item used
 * (addons/web/static/src/webclient/user_menu/user_menu_items.js:20); OCA
 * disable_odoo_online removes that item, so the slot is free and Help keeps
 * its familiar position at the top of the menu.
 *
 * The url comes from session_info rather than being hard-coded here, so
 * brand.py stays the single source of truth (models/ir_http.py).
 */
function afendaHelpItem(env) {
    const url = session.afenda_docs_url;
    return {
        type: "item",
        id: "afenda_help",
        description: _t("Help"),
        href: url,
        show: () => Boolean(url),
        callback: () => {
            browser.open(url, "_blank");
        },
        sequence: 20,
    };
}

registry.category("user_menuitems").add("afenda_help", afendaHelpItem);
