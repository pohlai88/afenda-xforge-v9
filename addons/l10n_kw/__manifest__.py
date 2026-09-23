{
    'name': 'Kuwait - Accounting',
    'countries': ['kw'],
    'description': """
This is the base module to manage the accounting chart for Kuwait in AFENDA xForge.
===================================================================================
Kuwait accounting basic charts and localization.
Activates:
- Chart of accounts
    """,
    'category': 'Accounting/Localizations/Account Charts',
    'version': '1.0',
    'depends': [
        'account',
        'l10n_gcc_invoice',
    ],
    'auto_install': ['account'],
    'demo': [
        'demo/demo_company.xml',
    ],
    'author': 'AFENDA xForge S.A.',
    'license': 'LGPL-3',
}
