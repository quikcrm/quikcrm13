# -*- coding: utf-8 -*-

from odoo import models, fields,api,_
from odoo.exceptions import UserError, ValidationError
from lxml import etree

class AssignTarget(models.Model):
    _name='assign.target'
#    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _rec_name='user_id'
    _order='id desc'
    _description = "Target"
    
    user_id=fields.Many2one('res.users',string='Salesperson',track_visibility='onchange')
    company_id=fields.Many2one('res.company',default=lambda self:self.env.user.company_id)
    currency_id=fields.Many2one('res.currency',related='company_id.currency_id')
    target=fields.Float('Target Revenue',track_visibility='onchange')
    target_bottom=fields.Float('Target Bottom Line Revenue',track_visibility='onchange')
    won_target=fields.Float('Won Revenue',compute='_compute_revenue')
    won_percent=fields.Float(compute='_compute_revenue')
    won_bottom=fields.Float('Won Bottom Line Revenue',compute='_compute_revenue')
    bottom_percent=fields.Float(compute='_compute_revenue')
    date_from=fields.Date('Date From',default=fields.Date.context_today)
    date_to=fields.Date('Date To')
    state=fields.Selection([('draft','Draft'),('done','Done')],string='Status',default='draft',track_visibility='onchange')

    target_str = fields.Char('Target Revenue Str', compute='_num_to_words_target')
    won_target_str = fields.Char('Won Revenue Str', compute='_num_to_words_won_target')
    target_bottom_str = fields.Char('Target Bottom Line Revenue Str', compute='_num_to_words_target_bottom')
    won_bottom_str = fields.Char('Won Bottom Line Revenue Str', compute='_num_to_words_won_bottom')
    
    @api.constrains('user_id', 'date_from','date_to')
    def _existing_target(self):
        for target in self:
            target_id=self.sudo().search([('user_id','=',target.user_id.id),('date_from','>=',target.date_from),('date_to','<=',target.date_to),('id','!=',target.id)])
            if target_id:
                raise ValidationError(_('You can not assign target for the same month to same salesperson.'))
            
    # @api.model
    # def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
    #     res = super(AssignTarget, self).fields_view_get(view_id=view_id, view_type=view_type,toolbar=toolbar, submenu=submenu)
    #     doc = etree.XML(res['arch'])
    #     if self.env.uid!=1:
    #         for node_form in doc.xpath("//tree"):
    #             node_form.set("import", 'false')
    #     res['arch'] = etree.tostring(doc)
    #     return res

    # @api.multi
    def _compute_revenue(self):
        Lead=self.env['crm.lead']
        for rec in self:
            if rec.state=='done':
                lead_id=Lead.sudo().search([('user_id','=',rec.user_id.id),('date_won','>=',rec.date_from),('date_won','<=',rec.date_to)])
                rec.won_target=sum(l.planned_revenue for l in lead_id)
#                rec.sudo().write({'won_target_value':rec.won_target})
                rec.won_bottom=sum(l.bottom_line for l in lead_id)
#                rec.sudo().write({'won_bottom_value':rec.won_bottom})
                rec.won_percent=((rec.won_target/rec.target)*100 if rec.won_target > 0 else 0)
                rec.bottom_percent=((rec.won_bottom/rec.target)*100 if rec.won_target > 0 else 0)
            else:
                rec.won_target=0
#                rec.sudo().write({'won_target_value':rec.won_target})
                rec.won_bottom=0
#                rec.sudo().write({'won_bottom_value':rec.won_bottom})
                rec.bottom_percent=0
                rec.won_percent=0

    # @api.multi
    def _num_to_words_target(self):
        for target in self:
            int_value = int(target.target)
            target.target_str = self._num_to_words(int_value)

    # @api.multi
    def _num_to_words_won_target(self):
        for target in self:
            int_value = int(target.won_target)
            target.won_target_str = self._num_to_words(int_value)

    # @api.multi
    def _num_to_words_target_bottom(self):
        for target in self:
            int_value = int(target.target_bottom)
            target.target_bottom_str = self._num_to_words(int_value)

    # @api.multi
    def _num_to_words_won_bottom(self):
        for target in self:
            int_value = int(target.won_bottom)
            target.won_bottom_str = self._num_to_words(int_value)

    # @api.multi
    def _num_to_words(self, int_value):

        target_list = [int(x) for x in str(int_value)]

        if len(target_list) >= 9:
            listToStr = ''.join([str(elem) for elem in target_list[:2]])
            return listToStr + ' ' + 'Cr'

        if len(target_list) == 8:
            listToStr = ''.join([str(elem) for elem in target_list[:1]])
            return listToStr + ' ' + 'Cr'

        if len(target_list) == 7:
            listToStr = ''.join([str(elem) for elem in target_list[:2]])
            return listToStr + ' ' + 'L'

        if len(target_list) == 6:
            listToStr = ''.join([str(elem) for elem in target_list[:1]])
            return listToStr + ' ' + 'L'

        if len(target_list) == 5:
            listToStr = ''.join([str(elem) for elem in target_list[:2]])
            return listToStr + ' ' + 'K'

        if len(target_list) == 4:
            listToStr = ''.join([str(elem) for elem in target_list[:1]])
            return listToStr + ' ' + 'K'
            