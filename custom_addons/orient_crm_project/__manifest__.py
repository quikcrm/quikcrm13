# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Orient CRM Project',
    'version': '1.1',
    'category': 'CRM',
    'summary': 'Assigning leads to purchase and scm',
    'description': "CRM",
    'author': 'Orient Technologies Pvt Ltd',
    'images': [
    ],
    'depends': [
        'project',
        'orient_crm'
    ],
    'data': [
        'data/project_data.xml',
        # 'security/orient_crm_security.xml',
        # 'wizard/confirm_wizard_view.xml',
        # 'security/ir.model.access.csv',
        'views/crm_project_view.xml',
    ],
    'demo': [
    ],
    'installable': True,
    'application': True,
    'auto_install': True,
    'qweb': [],
}