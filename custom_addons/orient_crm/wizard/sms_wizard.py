# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _,api
import requests
import logging
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError, Warning
_logger = logging.getLogger(__name__)

class SMSWizard(models.TransientModel):
    _name = 'sms.wizard'
    _description = 'Wizard for sending sms to the clients'


    partner_ids = fields.Many2many('res.partner','sms_wizard_rel','wizard_id','partner_id',string="Contacts") 
    sms_body=fields.Text(string="Message")
    single=fields.Boolean(string="Single(SMS)")
    mobile=fields.Char(size=10,string="Mobile No.")
    
    # @api.multi
    def send_sms(self):
        if self.single:
            if self.mobile:
                mobile=self.mobile
                if len(mobile)!=10 or not mobile.isdigit():
                    raise UserError(_('Mobile number is not valid %s')%(self.mobile))
                else:
                    try:
                        req=requests.get('http://103.209.99.7/sendsms/sendsms.php?username=%s&password=%s&type=TEXT&sender=%s&mobile=%s&message=%s'%('OrientTech','gpaznQLt','QKFRMZ',self.mobile,self.sms_body))
                        _logger.info('%s with mobile %s'%(req,self.mobile))
                    except Exception as e:
                        raise UserError(_('Exception occured %s with mobile number %s')%(e,self.mobile))
        else:
            for rec in self.partner_ids:
                if rec.mobile:
                    mobile=rec.mobile
                    if len(mobile)!=10 or not mobile.isdigit():
                        raise UserError(_('Mobile number is not valid %s')%(rec.mobile))
                    else:
                        try:
                            req=requests.get('http://103.209.99.7/sendsms/sendsms.php?username=%s&password=%s&type=TEXT&sender=%s&mobile=%s&message=%s'%('OrientTech','gpaznQLt','QKFRMZ',rec.mobile,self.sms_body))
                            _logger.info('%s with mobile %s'%(req,rec.mobile))
                        except Exception as e:
                            raise UserError(_('Exception occured %s with mobile number %s')%(e,rec.mobile))
        return True
        