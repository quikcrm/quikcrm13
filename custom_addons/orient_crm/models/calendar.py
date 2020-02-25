# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo import SUPERUSER_ID
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from odoo.exceptions import UserError, AccessError, ValidationError


class Meeting(models.Model):

	_inherit = "calendar.event"

	# is_presales = fields.Boolean(string='Pre-sales', compute='_compute_is_presales', store=True)
	is_presales = fields.Boolean(string='Pre-sales')

	# @api.depends('name')
	# def _compute_is_presales(self):
	# 	print("@@@@@@@@@@@@@@@@@")
	# 	# all_presales_events = self.search([('is_presales','=',True)])
	# 	for event in self:
	# 		if self.env.user.has_group('calendar.group_own_calendar'):
	# 			event.is_presales = True
	# 		else:
	# 			event.is_presales = False

	@api.model
	def create(self, vals):
		res=super(Meeting,self).create(vals)
		for partner in res.partner_ids:
			user = self.env['res.users'].search([('partner_id','=',partner.id)])
			if user.has_group('calendar.group_own_calendar'):
				res.is_presales = True
			else:
				res.is_presales = False
		return res

	# @api.multi
	def write(self,vals):
		#       Check for the existing user
		if vals.get('partner_ids'):
			partners = vals.get('partner_ids')[0]
			for partner in partners:
				users = self.env['res.users'].search([('partner_id','=',partner)])
				for user in users:
					if user.has_group('calendar.group_own_calendar'):
						self.is_presales = True
					else:
						self.is_presales = False
		return super(Meeting,self).write(vals)
