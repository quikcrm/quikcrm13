# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


from odoo import api, fields, models, tools, SUPERUSER_ID, _
from odoo.exceptions import UserError, AccessError, ValidationError


class Task(models.Model):
    _inherit = "project.task"

    p_bu_id = fields.Many2one('crm.bu', string="BU", readonly=True)
    p_sub_bu_id = fields.Many2one('crm.sub.bu', string="Sub BU", readonly=True)
    p_top_line = fields.Float('Top Line')
    p_bottom_line = fields.Float('Bottom Line')
    p_partner_id = fields.Many2one('res.partner', string="Company", readonly=True)
    p_vendor_id = fields.Many2one('crm.vendor', string="Vendor", readonly=True)
    distributor = fields.Char('Distributor')
    final_bottom_line = fields.Float('Final Bottom Line')
    po_number = fields.Char(string="PO Number")
    so_number = fields.Char(string="SO Number")
    order_line = fields.One2many('project.order.line', 'order_id', string='Product Lines', copy=True, auto_join=True)


class ProjectOrderLine(models.Model):
    _name = 'project.order.line'
    _description = 'Project Order Line'

    name = fields.Char(string='Product', required=True)
    order_id = fields.Many2one('project.task', string='Order Reference', required=True, ondelete='cascade', index=True, copy=False)
    # product_id = fields.Many2one('product.product', string='Product', change_default=True, ondelete='restrict', required=True)
    top_line = fields.Float('Top Line')
    bottom_line = fields.Float('Initial Bottom Line')
    final_bottom_line = fields.Float('Final Bottom Line')


class CRM(models.Model):
    _inherit = "crm.lead"

    # @api.multi
    def write(self,vals):
        # print("\n\n self::: ", self, "\n\n vals::: ", vals)
        if vals.get('stage_id') == 4:
            purchase = self.env['project.project'].search([('name','=','Purchase')])
            vals_tasks = {'name': self.name,
            'p_bu_id': self.crm_bu_id.id,
            'p_sub_bu_id': self.crm_sub_bu_id.id,
            'p_top_line': self.planned_revenue,
            'p_bottom_line': self.bottom_line,
            'p_vendor_id': self.crm_vendor_id.id,
            'p_partner_id': self.partner_id.id,
            'project_id': purchase.id}
            lead_task = self.env['project.task'].create(vals_tasks)
            return super(CRM,self).write(vals)
        return super(CRM,self).write(vals)

