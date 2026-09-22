# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Romania - Accounting',
    'website': '/docs/applications/finance/fiscal_localizations/romania.html',
    'author': 'Fekete Mihai (NextERP Romania SRL), AFENDA xForge S.A.',
    'icon': '/account/static/description/l10n.png',
    'countries': ['ro'],
    'category': 'Accounting/Localizations/Account Charts',
    'version': '1.1',
    'depends': [
        'account',
        'base_vat',
        'account_edi_ubl_cii',
    ],
    'auto_install': ['account'],
    'description': """
This is the module to manage the Accounting Chart, VAT structure, Fiscal Position and Tax Mapping.
It also adds the Registration Number for Romania in AFENDA xForge.
================================================================================================================

Romanian accounting chart and localization.
    """,
    'data': [
        'views/res_partner_view.xml',
        'data/account_tax_report_data.xml',
        'data/res.bank.csv',
    ],
    'demo': [
        'demo/demo_company.xml',
    ],
    'license': 'LGPL-3',
}
