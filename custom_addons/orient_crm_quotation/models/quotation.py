# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


from odoo import api, fields, models, tools, SUPERUSER_ID, _
from odoo.exceptions import UserError, AccessError, ValidationError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_quote = fields.Boolean(default=False, string="Is Quote")
    bu_temp = fields.Many2one('crm.bu', string="BU", readonly=True)
    is_morden = fields.Boolean(string='Is Morden?')
    is_datacenter = fields.Boolean(string='Is Datacenter?')


    @api.onchange('bu_temp','is_datacenter')
    def onchange_bu_temp(self):
        print("\n\n onchange_partner_id called...", self.bu_temp.name)
        if self.bu_temp.name == 'Modern Workplace':
        	self.is_morden = True
        else:
        	self.is_morden = False

        if self.bu_temp.name == 'Data Center':
        	self.is_datacenter = True
        else:
        	self.is_datacenter = False


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    part_no = fields.Char(string="Part Number")
    # is_main = fields.Boolean(string="Main Product", default=False)
    # product_lines = fields.Many2many('sub.product.line', 'sale_order_line_product_rel', 'sub_line_id', 'product_line_id', string='Sub Products', copy=False)
    # bu_temp = fields.Many2one('crm.bu', related="order_id.bu_temp", store=True, string="BU")

    # @api.onchange('product_id')
    # def onchange_product_id(self):
    #     if self.product_id:
    #         print("\n\n onchange_product_id calleddddddddd")
    #         if self.is_main == True:
    #             self.product_uom_qty = 0.0
    #             self.price_unit = 0.0


    # @api.model
    # def create(self, values):
    #     line = super(SaleOrderLine, self).create(values)
    #     if line.is_main == True:
    #     	line.product_uom_qty = 0.0
    #     	line.price_unit = 0.0
    #     return line

    # @api.multi
    # def write(self, values):
    #     if self.is_main == True:
    #     	values['product_uom_qty'] = 0.0
    #     	values['price_unit'] = 0.0

    #     return super(SaleOrderLine, self).write(values)

    # class SubProductLine(models.Model):
    #     _name = "sub.product.line"

    #     name = fields.Text(required=True)

class ProductTemplate(models.Model):
    _inherit = "product.template"

    # is_main = fields.Boolean(string="Main Product", default=False)

    # @api.onchange('is_main')
    # def _onchange_is_main(self):
    #     print("_onchange_is_main of product template calledddddd3333333333333333333")
    #     if self.is_main == True:
    #         self.product_uom_qty = 0.0
    #         self.price_unit = 0.0

    # @api.model
    # def create(self, vals):
    #     print("create of product template calledddddd3333333333333333333")
    #     if self.is_main == True:
    #         vals['product_uom_qty'] = 0.0
    #         vals['price_unit'] = 0.0
    #     return super(ProductTemplate, self).create(vals)

    # @api.multi
    # def write(self, values):
    #     print("write of product template calledddddd3333333333333333333")
    #     if self.is_main == True:
    #         values['product_uom_qty'] = 0.0
    #         values['price_unit'] = 0.0

    #     return super(ProductTemplate, self).write(values)