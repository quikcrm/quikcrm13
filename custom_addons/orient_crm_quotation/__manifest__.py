# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Orient CRM Quotation',
    'version': '1.1',
    'category': 'CRM',
    'summary': 'Create Quotation from this module.',
    'description': "CRM",
    'author': 'Orient Technologies Pvt Ltd',
    'images': [
    ],
    'depends': [
        'sale_crm',
        'orient_crm'
    ],
    'data': [
        # 'data/project_data.xml',
        # 'security/orient_crm_security.xml',
        # 'wizard/confirm_wizard_view.xml',
        # 'security/ir.model.access.csv',
        'views/quotation_view.xml',
        'report/quotation_report_templates.xml',
    ],
    'demo': [
    ],
    'installable': True,
    'application': True,
    'auto_install': True,
    'qweb': [],
}