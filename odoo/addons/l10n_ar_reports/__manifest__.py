# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Argentinian Accounting Reports',
    'version': '1.0',
    'author': 'ADHOC SA',
    'category': 'Localization',
    'description': """
Functional
----------

Add VAT Book report which is a legal requirement in Argentine and that holds the VAT detail info of sales or purchases made in a period of time.

Also add a VAT summary report that is used to analyze invoicing


""",
    'depends': [
        'l10n_ar',
        'account_reports',
    ],
    'data': [
        'data/account_financial_report_data.xml',
        'report/account_ar_vat_line_views.xml',
        'security/ir.model.access.csv',
        'security/security.xml',
    ],
    'demo': [],
    'auto_install': True,
    'installable': True,
}
