import json

from odoo import http
from odoo.http import request

from odoo.addons.web.controllers import webmanifest

from ..brand import BRAND


class WebManifest(webmanifest.WebManifest):
    """Scoped-app manifests carry the AFENDA colors.

    `/web/manifest.webmanifest` is already recolored by web_pwa_customize from
    the settings written by the post-install hook; the per-app manifest behind
    the "install this app" page is not, and hard-codes the Odoo purple.
    """

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
