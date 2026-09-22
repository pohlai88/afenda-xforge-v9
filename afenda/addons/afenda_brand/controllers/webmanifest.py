import json

from odoo import http
from odoo.http import request

from odoo.addons.web_pwa_customize.controllers import webmanifest

from ..brand import BRAND


class WebManifest(webmanifest.WebManifest):
    """AFENDA colors and icon shape for both PWA manifests.

    `/web/manifest.webmanifest` is already recolored by web_pwa_customize from
    the settings written by the post-install hook, but its icons declare no
    `purpose`, so Android crops them into a circle instead of using the full
    tile. The per-app manifest behind the "install this app" page is not
    recolored at all and hard-codes the Odoo purple.

    Extending the OCA controller rather than `web`'s keeps a single leaf class
    on the `/web/manifest.webmanifest` route, so the two overrides cannot be
    merged in an arbitrary order.
    """

    def _get_pwa_manifest_icons(self, pwa_icon):
        # The tile art keeps the mark inside the 80% safe zone, so the same
        # file serves as both a plain and a maskable icon.
        icons = super()._get_pwa_manifest_icons(pwa_icon)
        for icon in icons:
            icon["purpose"] = "any maskable"
        return icons

    @http.route(
        "/web/manifest.scoped_app_manifest",
        type="http",
        auth="public",
        methods=["GET"],
    )
    def scoped_app_manifest(self, app_id, path, app_name=""):
        response = super().scoped_app_manifest(app_id, path, app_name=app_name)
        manifest = json.loads(response.response[0])
        manifest["theme_color"] = BRAND["primary"]
        manifest["background_color"] = BRAND["paper"]
        return request.make_json_response(
            manifest, {"Content-Type": "application/manifest+json"}
        )
