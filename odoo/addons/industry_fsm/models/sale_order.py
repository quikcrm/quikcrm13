# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = ['sale.order']

    task_id = fields.Many2one('project.task', string="Task", help="Task from which quotation have been created")

class SaleOrderLine(models.Model):
    _inherit = ['sale.order.line']

    def _update_line_quantity(self, values):
        # YTI TODO: This method should only be used to post
        # a message on qty update, or to raise a ValidationError
        # Should be split in master 
        if self.env.context.get('fsm_no_message_post'):
            return
        super(SaleOrderLine, self)._update_line_quantity(values)
