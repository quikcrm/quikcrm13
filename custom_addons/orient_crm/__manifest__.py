# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Orient CRM',
    'version': '1.1',
    'category': 'CRM',
    'summary': 'Merging partners into one',
    'description': "CRM",
    'author': 'Orient Technologies Pvt Ltd',
    'images': [
    ],
    'depends': [
        'base','contacts','crm','mail','calendar','mass_mailing'
    ],
    'data': [
        'security/orient_crm_security.xml',
        'views/partner_view.xml',
        'views/res_users.xml',
        'views/import_partners_view.xml',
        'views/assign_target_view.xml',
        'views/crm_view.xml',
        'data/mail_template.xml',
        'data/res_partner_data.xml',
        'data/crm_lead_data.xml',
        'wizard/sms_wizard_view.xml',
#        'wizard/confirm_wizard_view.xml',
        'security/ir.model.access.csv',
    ],
    'demo': [
    ],
    'installable': True,
    'application': True,
    'auto_install': True,
    'qweb': [
        "static/src/xml/base.xml",
        ],
}
