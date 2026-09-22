import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

/**
 * Quiet by default: a finished action deserves one line of feedback, not a
 * cartoon. This replaces web's own "rainbow_man" entry
 * (addons/web/static/src/core/effects/effect_service.js:58), which the effect
 * service resolves by name for every `effect` an action returns, so every
 * caller in every addon is covered without patching any of them.
 *
 * Returning nothing tells the effect service there is no overlay component to
 * mount (effect_service.js:74).
 */
function afendaRainbowMan(env, params = {}) {
    let message = params.message;
    if (message instanceof Element) {
        // Upstream accepts (and deprecates) an element; a notification takes text.
        message = message.textContent;
    }
    env.services.notification.add(message || _t("Done."), { type: "success" });
}

registry.category("effects").add("rainbow_man", afendaRainbowMan, { force: true });
