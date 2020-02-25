# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from werkzeug.urls import url_encode

class ResPartner(models.Model):
    _inherit = "res.partner"

    def _get_doc_count(self):
        Attachment=self.env['ir.attachment']
        for rec in self:
            rec.doc_count=Attachment.sudo().search_count(['|','|',('res_id','=',rec.id),('lead_company_id','=',rec.id),('res_model','=','res.partner'),('res_model','=','crm.lead')])
    
    doc_count=fields.Integer(compute='_get_doc_count')
    
    @api.onchange('email','phone','mobile')
    def onchange_email_phone_mobie(self):
        if not self.email:
            self.email=False
            self.email_validation=False
        if not self.phone:
            self.phone=False
            self.phone_validation=False
        if not self.mobile:
            self.mobile=False
            self.mobile_validation=False
            
    @api.model
    def default_get(self, fields_list):
        defaults = super(ResPartner, self).default_get(fields_list)
        defaults['country_id']=self.env['res.company'].sudo().browse(defaults.get('company_id')).country_id.id
        return defaults
    
#    @api.onchange('name')
#    def _check_name(self):
#        if self.name:
#            com_name=self.name
#            name=com_name.split(' ')[0]
#            partner=self.sudo().search([('name','=ilike',name),('parent_id','=',False)],limit=1)
#            if partner and self.duplicated:
#                raise ValidationError(_('Company already exists in database with name " %s ".')%(partner.name))
            
#    @api.one
#    @api.constrains('name')
#    def _check_name_duplication(self):
#        if self.name:
#            com_name=self.name
#            name=com_name.split(' ')[0]
#            partner=self.sudo().search([('name','=ilike',name),('id','!=',self.id),('parent_id','=',False)],limit=1)
#            if partner and not self.duplicated:
#                raise ValidationError(_('Company already exists in database with name " %s ".\n If want to create duplicate company then select "Allow duplicate" option to proceed.')%(partner.name))
    
class CRM(models.Model):
    _inherit = "crm.lead"
    
    lead_category=fields.Selection([('hunting','Hunting'),('farming','Farming')],string='Lead Type')
    bottom_line=fields.Float('for Bottom Line')
    date_won=fields.Date('Date Won')
    demo_name=fields.Char('Demo')
    supplier_name=fields.Char('Vendor')

    crm_vendor_id = fields.Many2one('crm.vendor', string="Vendor")
    crm_bu_id = fields.Many2one('crm.bu', string="BU")
    crm_sub_bu_id = fields.Many2one('crm.sub.bu', string="Sub BU")
    user_ids = fields.Many2many('res.users', 'crm_lead_users_rel', 'lead_id', 'user_id', string="Share with", copy=False)
    doc_count = fields.Integer(compute='_get_doc_count')
    
    # @api.multi
    def action_set_won(self):
        """ add restriction here """
        Attachment=self.env['ir.attachment']
        for lead in self:
            lead_doc = Attachment.sudo().search([('res_model','=','crm.lead'),('res_id','=',lead.id)])

            is_po = False
            is_doc_uploaded = False
            for doc in lead_doc:
                if doc.lead_type == 'po':
                    is_po = True
                    if doc.datas:
                        is_doc_uploaded = True
            if lead.doc_count == 0 or is_po == False or is_doc_uploaded == False:
                raise ValidationError(_('Please upload a PO before moving into Won stage.'))
        return super(CRM,self).action_set_won()

    @api.onchange('stage_id')
    def _onchange_stage_id(self):
        """ returns the new values when stage_id has changed """
        # stage = self.env['crm.stage'].browse(self.stage_id)
        Attachment=self.env['ir.attachment']
        # if stage.on_change:
        if self.stage_id.name == 'Won':
            lead_doc = Attachment.sudo().search([('res_model','=','crm.lead'),('res_name','=',self.name)])
            is_po = False
            is_doc_uploaded = False

            for doc in lead_doc:
                if doc.lead_type == 'po':
                    is_po = True
                    if doc.datas:
                        is_doc_uploaded = True
            if is_po == False or is_doc_uploaded == False:
                raise ValidationError(_('Please upload a PO before moving into Won stage.'))
        return super(CRM,self)._onchange_stage_id()

    # @api.multi
    def action_set_won_rainbowman(self):
        self.write({'date_won':fields.Date.context_today(self)})
        return super(CRM,self).action_set_won_rainbowman()

    # @api.model
    # def _onchange_stage_id_values(self, stage_id):
    #     print("\n\n _onchange_stage_id_values calledddddddddddddd")
    #     """ returns the new values when stage_id has changed """
    #     stage = self.env['crm.stage'].browse(stage_id)
    #     Attachment=self.env['ir.attachment']

    #     if stage.on_change:
    #         if stage.name == 'Won':
    #             lead_doc = Attachment.sudo().search([('res_model','=','crm.lead'),('res_name','=',self.name)])
    #             is_po = False
    #             is_doc_uploaded = False

    #             for doc in lead_doc:
    #                 if doc.lead_type == 'po':
    #                     is_po = True
    #                     if doc.datas:
    #                         is_doc_uploaded = True
    #             if is_po == False or is_doc_uploaded == False:
    #                 raise ValidationError(_('Please upload a PO before moving into Won stage.'))
    #         return super(CRM,self)._onchange_stage_id_values(stage_id)
    
    # @api.one
    def _get_doc_count(self):
        Attachment=self.env['ir.attachment']
        for rec in self:
            rec.doc_count=Attachment.sudo().search_count([('res_model','=','crm.lead'),('res_id','=',rec.id)])

    def get_share_url(self):
        self.ensure_one()
        params = {
            'model': self._name,
            'res_id': self.id,
        }
        if hasattr(self, 'access_token') and self.access_token:
            params['access_token'] = self.access_token
        if hasattr(self, 'partner_id') and self.partner_id:
            params.update(self.partner_id.signup_get_auth_param()[self.partner_id.id])

        return '/mail/view?' + url_encode(params)

    def get_mail_url(self):
        return self.get_share_url()

    # def mail_template(self,user):
    #     template_id2 = self.env.ref('orient_employee_self_service_portal.email_template_for_birthday_reminder', False)
    #     self.env['mail.template'].browse(template_id2.id).send_mail(record.id, force_send=True)
    #     # template = self.env.ref('account.email_template_edi_invoice', False)
    #     template={
    #         'email_from':self.env.user.partner_id.email or '',
    #         'email_to':user.partner_id.email or '',
    #         'subject':'Lead: '+self.name,
    #         'body_html':'<p>Dear <strong>'+user.partner_id.name+',</strong><br/> '+self.env.user.name+' has assigned you a lead <strong>'+self.name+'</strong> for '+(self.partner_id.name if self.partner_id else '')+
    #                     '<br/> <br/><br/>'+ '<a style="background-color: #8080ff; margin-top: 10px; padding: 10px; text-decoration: none; color: #fff; border-radius: 5px; font-size: 16px;">View Lead</a>'
    #                     +'<br/><br/><br/>'+'Thank You,</p>'
    #     }
    #     self.env['mail.mail'].sudo().create(template).send()

    def mail_template(self,user):
        local_context = self.env.context.copy()
        local_context.update({
            'email_to': user.email or '',
            'body_html': 'Dear '+user.partner_id.name+','
        })
        template_id = self.env.ref('orient_crm.email_template_share_lead', False)
        template_id.with_context(local_context).send_mail(self.id, force_send=True)
        
#   Send mail to shared with user and it will update partner_id field value to partner parent_id
    @api.model
    def create(self,vals):
        if vals.get('partner_id'):
            partner_id=self.env['res.partner'].sudo().browse(vals.get('partner_id'))
            if partner_id.parent_id:
             vals['partner_id']=partner_id.parent_id.id  
        res=super(CRM,self).create(vals)
        if res.user_ids:
            for user in res.user_ids:
                res.mail_template(user)
        return res
    
#   Send mail to shared with user   
#     @api.multi
    def write(self,vals):
#       Check for the existing user
        existing_users=self.user_ids.ids
        if vals.get('user_ids'):
            users=vals.get('user_ids')[0]
            if users and len(users)==3:
                user_id=[user for user in users[2] if user not in existing_users]
                User=self.env['res.users'].sudo().browse(user_id)
                for u_id in User:
                    self.mail_template(u_id)
#       Send mail when satge changed
        # if  vals.get('stage_id'):
        #     for u_id in self.user_ids:
        #         self.mail_template(u_id)
        #     self.mail_template(self.user_id)
        return super(CRM,self).write(vals)


class CrmVendor(models.Model):
    _name = "crm.vendor"
    _description = 'vendors for the company'

    name = fields.Char('Name', required=True, translate=True)
    active = fields.Boolean('Active', default=True)

class CrmBu(models.Model):
    _name = "crm.bu"
    _description = 'BU for the company'

    name = fields.Char('Name', required=True, translate=True)
    active = fields.Boolean('Active', default=True)

class CrmSubBu(models.Model):
    _name = "crm.sub.bu"
    _description = 'Sub BU for the company'

    name = fields.Char('Name', required=True, translate=True)
    active = fields.Boolean('Active', default=True)
    crm_bu_id=fields.Many2one('crm.bu','Lead BUs')
    
class Attachment(models.Model):
    _inherit = "ir.attachment"
    
    lead_type=fields.Selection([('proposals','Proposals'),('po','PO'),('invoice','Invoice')],string='Document Type')
    contact_type=fields.Selection([('nda','NDA'),('sla','SLA')],string='Document Type')
    lead_company_id=fields.Integer('Partner ID')