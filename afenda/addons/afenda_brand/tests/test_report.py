import base64

from odoo.tests import HttpCase, tagged
from odoo.tools import file_open

from ..brand import BRAND

REPORT_BUNDLE = "web.report_assets_common"

# The static instances the PDF engine needs, and the weight each one must
# report. Generated from the variable fonts in static/fonts/ with
# fontTools.varLib.instancer; wkhtmltopdf ignores variable-font axes, so a VF
# asked for weight 600 silently prints its default weight instead.
STATIC_FONTS = {
    "SourceSans3-Regular.ttf": 400,
    "SourceSans3-Semibold.ttf": 600,
    "SourceSans3-Bold.ttf": 700,
    "SourceSans3-It.ttf": 400,
    "SourceSerif4-Semibold.ttf": 600,
    "SourceCodePro-Regular.ttf": 400,
}


@tagged("post_install", "-at_install")
class TestReport(HttpCase):
    """A printed AFENDA document: the standard layout, ink and graphite, and
    fonts the PDF engine can actually use."""

    def _report_css(self):
        urls = self.env["ir.qweb"]._get_asset_link_urls(REPORT_BUNDLE)
        self.assertTrue(urls, f"{REPORT_BUNDLE} links no stylesheet")
        return "".join(self.url_open(url).text for url in urls)

    def test_company_report_defaults(self):
        company = self.env.ref("base.main_company")
        self.assertEqual(company.font, "Source_Sans_3")
        self.assertEqual(
            company.external_report_layout_id,
            self.env.ref("web.external_layout_standard"),
        )
        # A document carries no action, so no Ledger Blue on it.
        self.assertEqual(company.primary_color.upper(), BRAND["ink"])
        self.assertEqual(company.secondary_color.upper(), BRAND["graphite"])

    def test_report_bundle_ships_static_fonts(self):
        css = self._report_css()
        # The Selection key is emitted raw as a CSS family name by
        # web.styles_company_report, so a face must be declared under it.
        self.assertIn("Source_Sans_3", css, "the company font family is not declared")
        for filename in STATIC_FONTS:
            url = f"/afenda_brand/static/fonts/{filename}"
            self.assertIn(url, css, f"{filename} is not referenced by the report bundle")
            self.assertEqual(self.url_open(url).status_code, 200, f"{url} is not served")
        # wkhtmltopdf would print every weight at the VF default.
        self.assertNotIn("-VF.ttf", css, "the report bundle must not use variable fonts")

    def test_report_bundle_has_document_rules(self):
        css = self._report_css()
        self.assertIn("tabular-nums", css, "report figures are not tabular")
        self.assertIn("Source Serif 4", css, "the display face is missing from documents")
        self.assertIn(BRAND["hairline"].lower(), css.lower(), "table rules are not hairline")

    def test_company_report_style_attachment(self):
        # web regenerates this attachment whenever a company report field is
        # written (addons/web/models/models.py:2241-2266). Its url carries no
        # leading slash (addons/web/data/report_layout.xml:52).
        attachment = self.env.ref("web.asset_styles_company_report").sudo()
        self.assertEqual(attachment.url, "web/static/asset_styles_company_report.scss")
        style = base64.b64decode(attachment.datas).decode()
        self.assertIn("Source_Sans_3", style, "the company style still names another font")
        self.assertIn(BRAND["ink"], style, "the company style is not drawn in ink")
        self.assertNotIn("Lato", style)

    def test_static_fonts_are_instances_not_variable(self):
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            self.skipTest("fontTools is not installed in this environment")
        for filename, weight in STATIC_FONTS.items():
            with file_open(f"afenda_brand/static/fonts/{filename}", "rb") as handle:
                font = TTFont(handle)
            self.assertNotIn("fvar", font, f"{filename} is still a variable font")
            self.assertEqual(
                font["OS/2"].usWeightClass, weight, f"{filename} reports the wrong weight"
            )
            italic = bool(font["OS/2"].fsSelection & 0b1)
            self.assertEqual(italic, filename.endswith("-It.ttf"), f"{filename} italic bit")

    def test_pdf_renders(self):
        report = self.env.ref("web.action_report_externalpreview")
        if report.get_wkhtmltopdf_state() != "ok":
            self.skipTest("wkhtmltopdf is not available")
        company = self.env.ref("base.main_company")
        # Under --test-enable the renderer short-circuits to HTML unless asked
        # for the real thing (odoo/addons/base/models/ir_actions_report.py:1030).
        pdf, content_type = report.with_context(
            force_report_rendering=True
        )._render_qweb_pdf(report, company.ids)
        self.assertEqual(content_type, "pdf")
        self.assertTrue(pdf.startswith(b"%PDF"), "the document did not render as a PDF")
