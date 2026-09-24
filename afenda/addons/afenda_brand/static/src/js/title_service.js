import { titleService } from "@web/core/browser/title_service";

const PRODUCT = "AFENDA xForge";

// The core title service falls back to "Odoo" when no part is set and shows
// only the action name otherwise. Keep the product name as the trailing part
// so the tab reads "Discuss - AFENDA xForge", and never "Odoo".
const originalStart = titleService.start;
titleService.start = function (...args) {
    const service = originalStart.apply(this, args);
    const setParts = service.setParts;
    service.setParts = (parts) => {
        // Parts keep insertion order: drop the suffix, apply the caller's
        // parts, then re-add it so the product name always comes last.
        setParts({ ...parts, zafenda: null });
        setParts({ zafenda: PRODUCT });
    };
    service.setParts({});
    return service;
};
