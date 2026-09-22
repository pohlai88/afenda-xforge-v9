import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("can_create_channel_from_form_view", {
    steps: () => [
        {
            trigger: ".o-mail-DiscussSidebarChannel-itemName:contains(AFENDA Bot)",
            run: "click",
        },
        {
            trigger: ".o-mail-DiscussContent-threadName[title='AFENDA Bot']",
        },
        { trigger: "button[title='View or join channels']:not(:visible)", run: "click" },
        {
            trigger: ".o_control_panel_main_buttons button:contains('New')",
            run: "click",
        },
        {
            trigger: "div[name='name'] input",
            run: "edit Test channel",
        },
        {
            trigger: ".breadcrumb-item:contains('AFENDA Bot')",
            run: "click",
        },
        {
            trigger: ".o-mail-DiscussSidebarChannel-itemName:contains('Test channel')",
        },
    ],
});
