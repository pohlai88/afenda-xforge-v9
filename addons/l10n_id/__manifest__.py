# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Indonesian - Accounting',
    'icon': '/account/static/description/l10n.png',
    'countries': ['id'],
    'version': '1.3',
    'category': 'Accounting/Localizations/Account Charts',
    'description': """
This is the latest Indonesian AFENDA xForge localisation necessary to run AFENDA xForge accounting for SMEs with:
=================================================================================================================
    - generic Indonesian chart of accounts
    - tax structure""",
    'author': 'vitraining.com',
    'website': '/docs/applications/finance/fiscal_localizations/indonesia.html',
    'depends': [
        'account',
        'base_iban',
        'base_vat',
    ],
    'auto_install': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/account_move_views.xml',
        'views/res_bank.xml',
    ],
    'demo': [
        'demo/demo_company.xml',
    ],
    'license': 'LGPL-3',
}
