# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo import SUPERUSER_ID
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from odoo.exceptions import UserError, AccessError, ValidationError
import datetime
from datetime import datetime, timedelta
from dateutil import *
from dateutil.relativedelta import relativedelta
from odoo.tools import float_compare
import logging
import math
import functools
import itertools
import psycopg2
from odoo.tools import config, human_size, ustr, html_escape
from odoo.tools.translate import _
from odoo.modules.module import get_module_resource
from dateutil.rrule import rrule, DAILY
import calendar
from collections import OrderedDict
from odoo.tools import mute_logger
import base64
import os
import shutil
from xlrd import open_workbook
_logger = logging.getLogger(__name__)


class Users(models.Model):
	_inherit = "res.users"

	team_leader_id = fields.Many2one('res.users', string='Team Leader')
	user_city = fields.Many2one('res.user.city', string="User city")
	password_reset = fields.Boolean('Password Reset?',default=False)

	def change_password(self, old_passwd, new_passwd):
		"""Change current user password. Old password must be provided explicitly
		to prevent hijacking an existing user session, or for cases where the cleartext
		password is not used to authenticate requests.

		:return: True
		:raise: odoo.exceptions.AccessDenied when old password is wrong
		:raise: odoo.exceptions.UserError when new password is not set or empty
		"""
		self.check(self._cr.dbname, self._uid, old_passwd)
		if new_passwd:
		    # use self.env.user here, because it has uid=SUPERUSER_ID
		    return self.env.user.write({'password': new_passwd, 'password_reset':True})
		raise UserError(_("Setting empty passwords is not allowed for security reasons!"))


class ResUserCity(models.Model):
    _name = 'res.user.city'
    _description = 'City'

    name = fields.Char()


class Partner(models.Model):
	_inherit = "res.partner"


	# def _default_is_company(self):
	# 	print("\n\n\n self is ::: ", self)
	# 	if self.parent_id:
	# 		print("\n\n\n in the if part ************")
	# 		print("\n\n\n self.parent_id ::: ", self.parent_id)
	# 		return False
	# 	else:
	# 		print("\n\n\n in the else part ************")
	# 		return True


	import_partner_id = fields.Many2one('import.partners', string='Import Form')
	origin_partner_id = fields.Many2one('res.partner')

	property_account_payable_id = fields.Many2one('account.account', company_dependent=True,
        string="Account Payable",
        domain="[('internal_type', '=', 'payable'), ('deprecated', '=', False)]",
        help="This account will be used instead of the default one as the payable account for the current partner",
        required=False)
	property_account_receivable_id = fields.Many2one('account.account', company_dependent=True,
        string="Account Receivable",
        domain="[('internal_type', '=', 'receivable'), ('deprecated', '=', False)]",
        help="This account will be used instead of the default one as the receivable account for the current partner",
        required=False)
	is_merged = fields.Boolean()
#	is_merged = fields.Boolean(default=True)
	is_company = fields.Boolean(string='Is a Company', default=True,
		help="Check if the contact is a company, otherwise it is a person")
#	industry = fields.Char(string='Industry')
	vat = fields.Char(string='GST Number')
	contributors = fields.Char(string='Account Manager', readonly=True, default=lambda self: self.env['res.users'].browse(self.env.uid).name)

	manpower = fields.Char(string='Total Manpower')
	turnover = fields.Char(string="Turnover")
	# bizarea = fields.Char(string='Biz Pain Area')
	branches = fields.Char(string='Total Branches')
	spend = fields.Char(string='Yearly IT Spend')
	# initiative = fields.Char(string='IT Initiative')

	brand = fields.Char(string='Brand in use')
	data_center = fields.Char(string='Data Center')
	network_security = fields.Char(string='Network Security')
	solution = fields.Char(string='Client Solution')

    # Application Setup
	apps = fields.Char(string='Core Apps')
	tools = fields.Char(string='BI Tools')
	bi_access = fields.Char(string="No. of users given access to BI")
	bi_challenge = fields.Char(string="Challenges faced by business users for BI")
	bi_it_challange = fields.Char(string="Challenges faced by IT users for BI")
	data_warehouse = fields.Char(string="Does customer have a data warehouse or datalake? Which one?")
	app_deploye = fields.Char(string="Is customer applications deployed on cloud or on-prem?")
	mob_app = fields.Char(string="Does customer have mobile applications for his core/legacy apps?")
	workforce = fields.Char(string="Does customer have workforce mobility app?")
	no_of_users = fields.Char(string="No. of users")
	inhouse_team = fields.Char(string="Does customer have in-house development team?")
	s_crm = fields.Char(string="CRM")
	s_hrms = fields.Char(string="HRMS")
	s_mdm = fields.Char(string="MDM")
	bz_apps = fields.Char(string='Bizz Apps')
	web_apps = fields.Char(string='Web Apps')
	others = fields.Char(string='Others')
	contact_tag_ids = fields.Many2many('res.partner.type.tag', 'res_partner_res_partner_type_tag_rel', 'partner_id', 'tag_id', string='Contact Type')
	email_validation=fields.Boolean('Email (✔/✘)')
	mobile_validation=fields.Boolean('Mobile (✔/✘)')
	phone_validation=fields.Boolean('Phone (✔/✘)')
	birth_date=fields.Date('Birth Date')
	aniv_date=fields.Date('Anniversary Date')

	#for delete contact which needs approval
	state = fields.Selection([
		('draft', 'To Submit'),
		('confirm', 'To Approve'),
		('refuse', 'Refused'),
		('validate', 'Approved')
		], string='Status', readonly=True, track_visibility='onchange', copy=False, default='draft',
			help="The status is set to 'To Submit', when a leave request is created." +
			"\nThe status is 'To Approve', when leave request is confirmed by user." +
			"\nThe status is 'Refused', when leave request is refused by manager." +
			"\nThe status is 'Approved', when leave request is approved by manager.")
	can_reset = fields.Boolean('Can reset', compute='_compute_can_reset', default=False)
	can_delete = fields.Boolean('Can Delete', default=False)

	# Services
	fms_vendor = fields.Char(string='Current FMS Vendor')
	skills_required = fields.Char(string="Skills/Resources Required")
	fms_renewal = fields.Char(string="FMS Renewal Month & Year")
	mvs_vendor = fields.Char(string="Current MVS Vendors")
	mvs_renewal = fields.Char(string="MVS Renewal Month & Year")
	sd_deployed = fields.Char(string="Current SD-WAN Deployed")
	mail_sol_deployed = fields.Char(string="Current Mailing Solution Deployed")
	mail_box = fields.Char(string="Number of Mail Box")
	vapt_vendor = fields.Char(string="Current VAPT Vendor")
	vapt_budget = fields.Char(string="Budget for VAPT")
	vapt_renweal = fields.Char(string="VAPT Renewal Month & Year")
	service_renewal = fields.Char(string="Service Opportunities for Renewal")
	renewal_product = fields.Char(string="Renewal Product")
	renewal_month_year = fields.Char(string="Renewal Month & Year")
	itsm_tool = fields.Char(string="ITSM Tool used")
	itsm_renewal_month = fields.Char(string="ITSM Renewal Month & Year")
	noc_service = fields.Char(string="NOC Services used")
	noc_renewal = fields.Char(string="NOC Renewal Month & Year")
	ps_vendor = fields.Char(string="Current PS Vendor")
	ps_skills = fields.Char(string="PS Resource skills deployed/required")
	contact_center = fields.Char(string="Contact Center Services used")
	contact_center_des = fields.Char(string="Contact Center Service Description")
	contact_center_vendor = fields.Char(string="Contact Center Current Vendor")
	contact_center_renewal = fields.Char(string="Contact Center Renewal")
	cust_server = fields.Char(string="Is customer having more then 10 servers?")
	oem_server = fields.Char(string="Current Vendor / OEM for Servers and Storage?")
	opex_offer = fields.Char(string="Is customer interested in OPEX offering for IT Infra")
	ites_setup = fields.Char(string='ITES Setup')
	email_solution = fields.Char(string='Email Solutions')
	cloud = fields.Char(string='Cloud Services')
	origin_ids = fields.One2many('res.partner', 'origin_partner_id', help="Reference of the document that created the registration, for example a contact")

	@api.model
	def _birthday_anivarsary_reminders(self):
#            Search all contacts for sending mails
            contact_ids=self.sudo().search([('parent_id','!=',False),('active','=',True)])
            
            if contact_ids:
                today = datetime.now()
                today_day = today.day
                today_month = today.month
                
                for contact in contact_ids:
#                    Condition for Birtdate
                    if contact.birth_date:
                        birth_datetime=datetime.strptime(contact.birth_date,DF)
                        birt_day=birth_datetime.day
                        birt_month=birth_datetime.month
                        if birt_day==today_day and birt_month==today_month:
                            birtday_template = self.env.ref('orient_crm.email_template_bithday_wish', False)
                            self.env['mail.template'].browse(birtday_template.id).send_mail(contact.id, force_send=True)
#                    Condition for Aniversary
                    if contact.aniv_date:
                        aniv_datetime=datetime.strptime(contact.aniv_date,DF)
                        aniv_day=aniv_datetime.day
                        aniv_month=aniv_datetime.month
                        if aniv_day==today_day and aniv_month==today_month:
                            aniversary_template = self.env.ref('orient_crm.email_template_anivarsary_wish', False)
                            self.env['mail.template'].browse(aniversary_template.id).send_mail(contact.id, force_send=True)
            return True
            
	@api.model
	def create(self, vals):
		if vals.get('parent_id'):
			vals['is_company'] = False
		else:
			vals['is_company'] = True
		vals['user_id'] = self.env.user.id
		return super(Partner, self).create(vals)

	# @api.multi
	def unlink(self):
		for partner in self.filtered(lambda partner: (partner.state in ['draft', 'confirm', 'refuse']) and (partner.can_delete == False)):
			raise UserError(_('You can delete a company/contact which is in "Approved" state') + ('\n') + ('Please click "Request for delete contact" to approve it from Reporting Manager'))
		return super(Partner, self).unlink()

	# @api.multi
	# @api.depends('name', 'is_company')
	# def name_get(self):
	# 	res = []
	# 	is_company_true_res = []
	# 	for record in self:
	# 		name = record.name
	# 		if record.is_company:
	# 			is_company_true_res.append((record.id, name))
	# 		else:
	# 			res.append((record.id, name))
	# 	return res

	# @api.one
	# @api.depends('parent_id')
	# def _compute_is_company(self):
	# 	print("\n\n self is ::: ", self.parent_id)
	# 	if self.parent_id:
	# 		is_company = False
	# 	else:
	# 		is_company = True

	# @api.depends('is_merged')
 #	def _partner_is_merged(self):
 #		print("\n\n ************", self)
		# Merged_partner = self.env['res.partner']
		# if self.is_merged:
		#     offer_letter_sent = False
		#     state = 'hr'
		# else:
		#     offer_letter_sent = True
		#     state = 'hr'
		# data['offer_letter_sent'] = offer_letter_sent
		# data['state'] = state
		# return {'value':data}

	# @api.multi
	def _compute_can_reset(self):
		""" User can reset a leave request if it is its own leave request
		    or if he is an Hr Manager.
		"""
		user = self.env.user
		print("comput callessssssssssssssssssssssssss")
		group_contact_manager = self.env.ref('orient_crm.group_manage_contacts')
		for partner in self:
			if group_contact_manager in user.groups_id or partner.user_id == user:
				partner.can_reset = True

	# @api.multi
	def action_confirm_delete(self):
		for partner in self:
			if partner.state == 'draft':
				partner.write({'state': 'confirm'})
			if partner.state == 'validate':
				partner.can_delete = True
		# if self.filtered(lambda partner: partner.state == 'draft'):
		# 	self.write({'state': 'confirm'})
		# if self.filtered(lambda partner: partner.state == 'validate'):
		# 	self.can_delete = True

	# @api.multi
	def action_confirm(self):
		if self.filtered(lambda partner: partner.state != 'draft'):
		    raise UserError(_('Delete request must be in Draft state ("To Submit") in order to confirm it.'))
		return self.write({'state': 'confirm'})

	# @api.multi
	def _check_security_action_approve(self):
		if not self.env.user.has_group('orient_crm.group_manage_contacts'):
			raise UserError(_('Only Manager can approve delete requests.'))

	# @api.multi
	def action_approve(self):
		# if not double_validation: this method calls action_validate() below
		self._check_security_action_approve()

		current_user = self.env['res.users'].search([('user_id', '=', self.env.uid)], limit=1)
		for partner in self:
			if partner.state != 'confirm':
				raise UserError(_('Delete request must be confirmed ("To Approve") in order to approve it.'))
			partner.action_validate()

	# @api.multi
	def _check_security_action_validate(self):
		if not self.env.user.has_group('orient_crm.group_manage_contacts'):
			raise UserError(_('Only Manager can approve delete requests.'))

	# @api.multi
	def action_validate(self):
		self._check_security_action_validate()

		current_user = self.env['res.users'].search([('user_id', '=', self.env.uid)], limit=1)
		for partner in self:
			if partner.state not in ['confirm']:
				raise UserError(_('Delete request must be confirmed in order to approve it.'))

			partner.write({'state': 'validate'})
		return True

	# @api.multi
	def _check_security_action_refuse(self):
		if not self.env.user.has_group('orient_crm.group_manage_contacts'):
			raise UserError(_('Only Manager can refuse leave requests.'))

	# @api.multi
	def action_refuse(self):
		self._check_security_action_refuse()

		current_user = self.env['res.users'].search([('user_id', '=', self.env.uid)], limit=1)
		for partner in self:
		    if partner.state not in ['confirm', 'validate']:
		        raise UserError(_('Delete request must be confirmed or validated in order to refuse it.'))

		    partner.write({'state': 'refuse'})

		return True

	# @api.multi
	def action_draft(self):
		for partner in self:
		    if not partner.can_reset:
		        raise UserError(_('Only Manager or the concerned employee can reset to draft.'))
		    if partner.state not in ['confirm', 'refuse']:
		        raise UserError(_('Delete request state must be "Refused" or "To Approve" in order to reset to Draft.'))
		    partner.write({'state': 'draft'})
		return True


class Tags(models.Model):

	_name = 'res.partner.type.tag'
	_description = 'Partner Tags - These tags can be used on contact to find customers by sector, or ... '

	name = fields.Char('Name', required=True, translate=True)
	color = fields.Integer('Color Index', default=10)

	_sql_constraints = [
	    ('name_uniq', 'unique (name)', "Tag name already exists !"),
	]


class MergePartnerAutomatic(models.TransientModel):
	_inherit = 'base.partner.merge.automatic.wizard'


	@api.model
	def _update_values(self, src_partners, dst_partner, new_partner):
		""" Update values of dst_partner with the ones from the src_partners.
		:param src_partners : recordset of source res.partner
		:param dst_partner : record of destination res.partner
		"""
		_logger.debug('_update_values for dst_partner: %s for src_partners: %r', dst_partner.id, src_partners.ids)

		model_fields = dst_partner.fields_get().keys()

		def write_serializer(item):
			if isinstance(item, models.BaseModel):
				return item.id
			else:
				return item
			# get all fields that are not computed or x2many
			values = dict()
			for column in model_fields:
				field = dst_partner._fields[column]
				if field.type not in ('many2many', 'one2many') and field.compute is None:
					for item in itertools.chain(src_partners, [dst_partner]):
						if item[column]:
							values[column] = write_serializer(item[column])

			# remove fields that can not be updated (id and parent_id)
			values.pop('id', None)
			parent_id = values.pop('parent_id', None)
			new_partner.write(values)

			# try to update the parent_id
			if parent_id and parent_id != new_partner.id:
				try:
					new_partner.write({'parent_id': parent_id})
				except ValidationError:
					_logger.info('Skip recursive partner hierarchies for parent_id %s of partner: %s', parent_id, new_partner.id)

	def _merge(self, partner_ids, dst_partner=None):
		""" private implementation of merge partner
		:param partner_ids : ids of partner to merge
		:param dst_partner : record of destination res.partner
		"""
		print("\n\n Merged_partner of orient_crm calledddddddddddddddddddddddddd")
		Partner = self.env['res.partner']
		partner_ids = Partner.browse(partner_ids).exists()
		if len(partner_ids) < 2:
			return

		if len(partner_ids) > 3:
			raise UserError(_("For safety reasons, you cannot merge more than 3 contacts together. You can re-open the wizard several times if needed."))

		# check if the list of partners to merge contains child/parent relation
		child_ids = self.env['res.partner']
		for partner_id in partner_ids:
			child_ids |= Partner.search([('id', 'child_of', [partner_id.id])]) - partner_id
		if partner_ids & child_ids:
			raise UserError(_("You cannot merge a contact with one of his parent."))

		# check only admin can merge partners with different emails
		if SUPERUSER_ID != self.env.uid and len(set(partner.email for partner in partner_ids)) > 1:
			raise UserError(_("All contacts must have the same email. Only the Administrator can merge contacts with different emails."))

		# remove dst_partner from partners to merge
		if dst_partner and dst_partner in partner_ids:
			src_partners = partner_ids - dst_partner
		else:
			ordered_partners = self._get_ordered_partner(partner_ids.ids)
			dst_partner = ordered_partners[-1]
			src_partners = ordered_partners[:-1]
		_logger.info("dst_partner: %s", dst_partner.id)

		# FIXME: is it still required to make and exception for account.move.line since accounting v9.0 ?
		if SUPERUSER_ID != self.env.uid and 'account.move.line' in self.env and self.env['account.move.line'].sudo().search([('partner_id', 'in', [partner.id for partner in src_partners])]):
			raise UserError(_("Only the destination contact may be linked to existing Journal Items. Please ask the Administrator if you need to merge several contacts linked to existing Journal Items."))
        
		_logger.info('(uid = %s) merged the partners %r with %s', self._uid, src_partners.ids, dst_partner.id)
		dst_partner.message_post(body='%s %s' % (_("Merged with the following partners:"), ", ".join('%s <%s> (ID %s)' % (p.name, p.email or 'n/a', p.id) for p in src_partners)))

		# delete source partner, since they are merged
		# src_partners.unlink()
		new_partner = Partner.create({
				'name': dst_partner.name,
				'is_company': True,
				'customer': False,
				'is_merged': True,
			})

		print("\n\n new_partner is ", new_partner)

		for partner_id in self.partner_ids:
			for child_id in partner_id.child_ids:
				new_child = Partner.create({
				'name': child_id.name,
				'parent_id': new_partner.id,
				'title': child_id.title.id,
				'function': child_id.function,
				'email': child_id.email,
				'phone': child_id.phone,
				'mobile': child_id.mobile,
				'comment': child_id.comment,
				'customer': False,
			})

		# call sub methods to do the merge
		self._update_values(src_partners, dst_partner, new_partner)

		dst_partner.is_merged = False
		for partner_id in src_partners:
			partner_id.is_merged = False

		cont_partners = self.env['res.partner'].search([('id', 'in', src_partners.ids)]).mapped('user_id').name
		print("\n\n cont_partners is ", cont_partners)

		new_partner.write({'contributors': (cont_partners + ' ' + dst_partner.user_id.name), 'origin_ids':[(6,0, src_partners.ids)]})
#		print("\n\n partners are::::  ", new_partner.origin_ids)


class ImportConfig(models.Model):
	_name = 'import.config'
	_description = "Import Configuration"

	source_path = fields.Char(string='Source Path')
	destination_path = fields.Char(string='Destination Path')
	failed_path = fields.Char(string='Failed File Path')


class ImportPartners(models.Model):
	_name = "import.partners"
	_description = "Import Partners"


	@api.model
	def _file_read(self, full_path, fname, bin_size=False):
		# import_config = self.env['import.config'].search([],limit=1)
		# source_path = '/home/odoouser/'
		# destination_path = '/home/odoouser/import_partners_done/'

		import_config = self.env['import.config'].search([],limit=1)
		source_path = str(import_config.source_path)
		destination_path = str(import_config.destination_path)
		print("\n\n in file read method :: ", source_path, destination_path)
		full_path = source_path

		# full_path = source_path
		r = ''
		try:
			if bin_size:
				r = human_size(os.path.getsize(full_path))
			else:
				r = base64.b64encode(open(full_path,'rb').read())
		except (IOError, OSError):
			_logger.info("_read_file reading %s", full_path, exc_info=True)
		return r


	# @api.depends('datas_fname','db_datas')
	# def _compute_datas(self):
	# 	bin_size = self._context.get('bin_size')
	# 	result = {}
	# 	for attach in self:
	# 		if attach.datas_fname:
	# 			result[attach.id] = self._file_read(attach.file_url,attach.datas_fname, bin_size)
	# 		else:
	# 			result[attach.id] = attach.db_datas


	@api.model
	def _file_write(self, value, file_name):
		db_datas = value
		bin_value = base64.b64decode(value)
		fname = file_name
		# import_config = self.env['import.config'].search([],limit=1)
		# source_path = '/home/kinjal/'
		# destination_path = '/home/odoouser/import_partners_done/'
		import_config = self.env['import.config'].search([],limit=1)
		source_path = str(import_config.source_path)
		destination_path = str(import_config.destination_path)
		full_path = source_path + fname
		if not os.path.exists(full_path):
			try:
				with open(full_path, 'wb') as fp:
					fp.write(bin_value)
					os.chmod(full_path,0o777)
					# shutil.chown(full_path, user='odoouser', group='odoouser')
			except IOError:
				_logger.info("_file_write writing %s", full_path, exc_info=True)
		return full_path


	# def _inverse_datas(self):
	# 	for attach in self:
	# 		# compute the fields that depend on datas
	# 		file_name = attach.datas_fname
	# 		fname = ''
	# 		# if not file_name:
	# 		# 	raise ValidationError(_('Please select file to import!!'))
	# 		value = attach.datas
	# 		bin_data = base64.b64decode(value) if value else b''
	# 		if file_name:
	# 			if file_name.endswith('.xls'):
	# 				fname = self._file_write(value,file_name)
	# 		vals = {'file_url':fname}
	# 		# write as superuser, as user probably does not have write access
	# 		super(ImportPartners, attach.sudo()).write(vals)


	name = fields.Char('Name',default="Import Partners")
	file_url = fields.Char('URL', index=True, size=1024)
	datas_fname = fields.Char('File Name')
	datas = fields.Binary(string='File')
	db_datas = fields.Binary('Database Data')
	partner_ids = fields.One2many('res.partner', 'import_partner_id', ondelete='restrict')


	# @api.multi
	def import_partners(self):
		if not self.datas_fname:
			raise ValidationError(_('Kindly select file for import!!'))
		# partner_obj = self.env['res.partner']
		# delete existing searched ids
		# existing_imported_partners = partner_obj.search([('import_partner_id','=',self.id)])
		# if existing_imported_partners:
			# existing_imported_partners.write({'import_partner_id': None})
		# datas_fname = str(self.datas_fname)

		Partner=self.env['res.partner']
		partner_field=Partner.fields_get()
		partner_vals=Partner.default_get(partner_field)

		file_datas = base64.decodestring(self.datas)
		workbook = open_workbook(file_contents=file_datas)
		sheet = workbook.sheet_by_index(0)
		data = [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]
		data.pop(0)
		file_data = data
		child_ids_dict = {}
		for row in file_data:
			if len(row) != 8:
				raise UserError(_('Insufficient columns !!'))
			# child_list = []
#			print("\n\n row is ::: ", row)

#			print('-------------',self.env.user)
			partner_vals = {
				'name':row[0],
				'is_company':True,
				'active':True,
				# 'is_company': True,
				'customer':False,
				'supplier':False,
				'user_id':self.env.user.id,
                                'create_uid':self.env.user.id,
                                'contributors':self.env.user.name,
				# 'employee':False,
				'industry':row[7],
				'company_type':'company',
				'type':'contact',
				'opt_out':False,
				'import_partner_id':self.id
			}
			# parent_id = partner_obj.create(parent_vals)
			child_vals = {
				'name':row[1],
				# 'parent_id':parent_id.id,
				'is_company':False,
				'active':True,
				'is_company':False,
				'customer':False,
				'company_type':'person',
				'supplier':False,
				'user_id':self.env.user.id,
                                'create_uid':self.env.user.id,
                                'contributors':self.env.user.name,
				# 'employee':False,
				'type':'contact',
				'function':row[2],
				'city':row[6],
				'email':row[3],
				'phone':int(row[5]) if isinstance(row[5],(int,float)) else row[5],
				'mobile':int(row[4]) if isinstance(row[4],(int,float)) else row[4] ,
				'opt_out':False,
			}
			l1=[(0,0,child_vals)]

			if child_ids_dict.get(row[0]):
				l2=child_ids_dict.get(row[0])['child_ids']
				child_ids_dict[row[0]].update({'child_ids':l1+l2})

			if not child_ids_dict.get(row[0]):
				partner_vals.update({'child_ids':l1})
				child_ids_dict[row[0]]=partner_vals

		for data in child_ids_dict.values():
#			print("\n\n ata is :::  ", data)
			com_name=data.get('name')
			name=com_name.split(' ')[0]
			partner=Partner.sudo().search([('name','=ilike',name),('id','!=',self.id),('parent_id','=',False)],limit=1)
			if partner:
                            continue
			partners = Partner.create(data)
#			partners.write({'user_id':self.env.user.id,'create_uid':self.env.user.id,'contributors':self.env.user.name})
#			for child in partners.child_ids:
#				child.write({'user_id':self.env.user.id,'create_uid':self.env.user.id,'contributors':self.env.user.name})
			# partner_obj.create(child_vals)

		# import_config = self.env['import.config'].search([],limit=1)
		# source_path = '/home/odoouser/'
		# destination_path = '/home/odoouser/import_partners_done/'

		# import_config = self.env['import.config'].search([],limit=1)
		# source_path = str(import_config.source_path)
		# print("\n\n &&&&&&&&&&&&&&&&&&&&&&&&&&source_path&&&&&&&&&&&&&&,,,, ", source_path)
		# destination_path = str(import_config.destination_path)
		# print("\n\n &&&&&&&&&&&&&&&&&&&&&&&&destination_path&&&&&&&&&&&&&&&&,,,, ", destination_path)
		# failed_path = str(import_config.failed_path)
		# file_path = source_path+datas_fname
		# print("\n\n file_path is :::  ", file_path)
		# print("\n\n datas_fname is :::  ", datas_fname)
		# workbook = open_workbook(file_path)
		# worksheet = workbook.sheet_by_index(0)
		# for row in range(1, worksheet.nrows):
		# 	print("row",row)
		# 	#column0--------------------------------------------------------------------------------------------
		# 	company_name = (worksheet.cell(row,0).value) 
		# 	if not company_name:
		# 		if os.path.isfile(file_path):
		# 			os.remove(file_path)
		# 		raise UserError(_('No/Improper company name %s !') % (company_name))
		# 	#column1--------------------------------------------------------------------------------------------
		# 	customer_name = (worksheet.cell(row,1).value)
		# 	if not customer_name:
		# 		if os.path.isfile(file_path):
		# 			os.remove(file_path)
		# 		raise UserError(_('No/Improper date of customer name %s !') % (customer_name))
		# 	#column2--------------------------------------------------------------------------------------------
		# 	designation = (worksheet.cell(row,2).value)
		# 	if not designation:
		# 		if os.path.isfile(file_path):
		# 			os.remove(file_path)
		# 		raise UserError(_('No/Improper date of designation %s !') % (designation))
		# 	#column3--------------------------------------------------------------------------------------------
		# 	email = (worksheet.cell(row,3).value)
		# 	if not email:
		# 		if os.path.isfile(file_path):
		# 			os.remove(file_path)
		# 		raise UserError(_('No/Improper email %s !') % (email))
		# 	# check_valid_email = is_valid_email(self,email)
		# 	# if not check_valid_email:
		# 	# 	if os.path.isfile('/home/odoouser/attendance/import_applications.xls'):
		# 	# 		os.remove('/home/odoouser/attendance/import_applications.xls')
		# 	# 	raise UserError(_('Invalid email %s ! Please correct it') % (email))
		# 	#column4--------------------------------------------------------------------------------------------
		# 	mobile = int((worksheet.cell(row,4).value))
		# 	if not mobile:
		# 		if os.path.isfile(file_path):
		# 			os.remove(file_path)
		# 		raise UserError(_('No/Improper mobile number %s !') % (mobile))
		# 	#column5--------------------------------------------------------------------------------------------
		# 	direct_landline = (worksheet.cell(row,5).value)
		# 	if not direct_landline:
		# 		if os.path.isfile(file_path):
		# 			os.remove(file_path)
		# 		raise UserError(_('No/Improper landline number %s !') % (direct_landline))
		# 	#column6--------------------------------------------------------------------------------------------
		# 	city = (worksheet.cell(row,6).value)
		# 	if not city:
		# 		if os.path.isfile(file_path):
		# 			os.remove(file_path)
		# 		raise UserError(_('No/Improper city %s !') % (city))
		# 	print("row details-----",company_name,customer_name,designation,email,mobile,direct_landline,city)
		# # self.write({'imported':True})
		# if os.path.isfile(file_path):
		# 	print("\n\n ************************* file_path is ", os.path.isfile(file_path))
		# 	print("\n\n destination111111", destination_path)
		# 	os.remove(file_path)
		# 	print("\n\n removed pth Is ::: ", file_path)
		# 	print("\n\n destination22222", destination_path)
		return True

	# @api.multi
	def assign_public_holidays(self):
		attendance_obj = self.env['hr.attendance']
		employee_obj = self.env['hr.employee']
		holiday_obj = self.env['holiday.master']
		holidays = []
		deleted_hol_ids = []
		# find out employees belonging to site locations first
		site_location_employees = []
		if self.site_location_master_ids:
			for each_line in self.site_location_master_ids:
				for employee_id in each_line.employee_ids:
					site_location_employees.append(employee_id.id)
		site_location_employees = list(set(site_location_employees))
		# find out employees of current site
		site_empl_ids = employee_obj.search([('site_master_id','=',self.id)])
		# find out deleted holidays
		if self.holiday_old_ids:
			holids = set(self.holiday_ids.ids)
			hololdids = set(self.holiday_old_ids.ids)
			deleted_hol_ids = list(hololdids-holids)	
		# if there are holidays to assign
		if self.holiday_ids:
			# iterate current site employees
			for site_empl_id in site_empl_ids:
				# check if current site employee is already in the site location list
				# if yes, ignore that employee. 
				if site_empl_id.id in site_location_employees:
					pass
				# if not find the attendance record 
				else:
					# if holidays are deleted, update the emp attendances of these holidays as AB
					if deleted_hol_ids:
						for each_deleted_hol_id in deleted_hol_ids:
							each_deleted_hol_id = holiday_obj.browse(each_deleted_hol_id)
							delhol_attendance_ids = attendance_obj.search([('employee_id','=',site_empl_id.id),('attendance_date','=',each_deleted_hol_id.holiday_date)])
							for delhol_attendance_id in delhol_attendance_ids:
								delhol_attendance_id.write({'employee_status':'AB'})	
					# iterate holidays
					for each_holiday_id in self.holiday_ids:
						holidays.append(each_holiday_id.id)
						# find attendance records
						existing_att_ids = attendance_obj.search([('employee_id','=',site_empl_id.id),('attendance_date','=',each_holiday_id.holiday_date)])
						if existing_att_ids:
							# if there is attendance record, update it with PH only if its AB or blank
							for existing_att_id in existing_att_ids:
								if existing_att_id.employee_status == 'AB' or existing_att_id.employee_status == None or existing_att_id.employee_status ==False or existing_att_id.employee_status==' ' or existing_att_id.employee_status=='':
									existing_att_id.write({'employee_status':'PH'})
						else:
							# if there is no attendance record, create one
							attendance_obj.create(
								{
									'employee_id':site_empl_id.id,
									'employee_code':site_empl_id.emp_code,
									'attendance_date':each_holiday_id.holiday_date,
									'department_id_val':site_empl_id.department_id.id,
									'site_master_id':self.id,
									'shift':site_empl_id.shift_id.id,
									'employee_status':'PH',
									'state':'draft',
									'created':True
								})
					# update holidays in employee profiles
					site_empl_id.write({'holiday_ids':[(6,0,holidays)]})
			# store holidays to old_holidays to figure out deleted holidays
			old_holidays = []
			if self.holiday_ids:
				for each_old_holiday in self.holiday_ids:
					old_holidays.append(each_old_holiday.id)
				self.write({'holiday_old_ids':[(6,0,old_holidays)]})
		# if not holidays assigned give access error
		else:
			raise AccessError("Nothing to assign!")


	# @api.multi
	def assign_site_location_holidays(self):
		attendance_obj = self.env['hr.attendance']
		employee_obj = self.env['hr.employee']
		holiday_obj = self.env['holiday.master']
		site_loc_emp_ids = []
		site_holiday_ids = []
		deleted_emp_ids = []
		deleted_hol_ids = []
		
		for each_site_holiday_id in self.holiday_ids:
			site_holiday_ids.append(each_site_holiday_id.id)

		for line1 in self.site_location_master_ids:
			for curr_emp_id in line1.employee_ids:
				site_loc_emp_ids.append(curr_emp_id.id)

		if site_loc_emp_ids and site_holiday_ids:
			for each_site_emp_id in site_loc_emp_ids:
				each_site_emp_id = employee_obj.browse(each_site_emp_id)
				each_site_emp_id.write({'holiday_ids':[(6,0,[])]})
				for each_site_holiday_id in site_holiday_ids:
					each_site_holiday_id = holiday_obj.browse(each_site_holiday_id)
					att_id = attendance_obj.search([('employee_id','=',each_site_emp_id.id),('attendance_date','=',each_site_holiday_id.holiday_date)])
					if att_id:
						att_id.write({'employee_status':'AB'})
		self.env.cr.commit()

		if self.site_location_master_ids:
			# update the deleted employees or holidays with AB
			# iterate over site_location_master_ids
			for line in self.site_location_master_ids:
				# if there are values in employee_old_ids, find out deleted employees
				if line.employee_old_ids:
					empids = set(line.employee_ids.ids)
					empoldids = set(line.employee_old_ids.ids)
					deleted_emp_ids = list(empoldids-empids)
				# if there are values in employee_old_ids, find out deleted holidays
				if line.holiday_old_ids:
					holids = set(line.holiday_ids.ids)
					hololdids = set(line.holiday_old_ids.ids)
					deleted_hol_ids = list(hololdids-holids)
				# if only employees are deleted, update the emp attendances with allocated holidays as AB
				if deleted_emp_ids and not deleted_hol_ids:
					for each_deleted_emp_id in deleted_emp_ids:
						each_deleted_emp_id = employee_obj.browse(each_deleted_emp_id)
						for holiday_id in line.holiday_ids:
							attendance_ids1 = attendance_obj.search([('employee_id','=',each_deleted_emp_id.id),('attendance_date','=',holiday_id.holiday_date)])
							for attendance_id1 in attendance_ids1:
								attendance_id1.write({'employee_status':'AB'})
				# if only holidays are deleted, update the emp attendances with deleted holidays as AB
				if deleted_hol_ids and not deleted_emp_ids:
					for each_deleted_hol_id in deleted_hol_ids:
						each_deleted_hol_id = holiday_obj.browse(each_deleted_hol_id)
						for emp_id in line.employee_ids:
							attendance_ids2 = attendance_obj.search([('employee_id','=',emp_id.id),('attendance_date','=',each_deleted_hol_id.holiday_date)])
							for attendance_id2 in attendance_ids2:
								attendance_id2.write({'employee_status':'AB'})
				# if both employees and holidays are deleted, update the deleted emp attendances with allocated holidays as AB
				if deleted_emp_ids and deleted_hol_ids:
					for each_deleted_emp_id in deleted_emp_ids:
						each_deleted_emp_id = employee_obj.browse(each_deleted_emp_id)
						for holiday_id in line.holiday_ids:
							attendance_ids3 = attendance_obj.search([('employee_id','=',each_deleted_emp_id.id),('attendance_date','=',holiday_id.holiday_date)])
							for attendance_id in attendance_ids:
								attendance_id3.write({'employee_status':'AB'})
				# assigning the site holidays to deleted employees
				if deleted_emp_ids:
					for each_deleted_emp_id in deleted_emp_ids:
						each_deleted_emp_id = employee_obj.browse(each_deleted_emp_id)
						each_deleted_emp_id.write({'holiday_ids':[(6,0,site_holiday_ids)]})
			self.env.cr.commit()
			# create or update attendance entries with PH
			# iterate over site_location_master_ids
			for line2 in self.site_location_master_ids:
				to_append = [] # list to store the holidays those are to be updated on employee profile
				holidays_to_compare = [] # list to store holidays to find out deleted holidays
				emp_to_compare = [] # list to store epmloyees to find out deleted employees
				for each_to_append in line2.holiday_ids:
					to_append.append(each_to_append.id)
					holidays_to_compare.append(each_to_append.id)
				for employee_id2 in line2.employee_ids:
					emp_to_compare.append(employee_id2.id)
					for holiday_id2 in line2.holiday_ids:
						attendance_id4 = attendance_obj.search([('employee_id','=',employee_id2.id),('attendance_date','=',holiday_id2.holiday_date)])
						if attendance_id4:
							attendance_id4.write({'employee_status':'PH'})
						else:
							attendance_vals = {
												'employee_id':employee_id2.id,
												'employee_code':employee_id2.emp_code,
												'attendance_date':holiday_id2.holiday_date,
												'department_id_val':employee_id2.department_id.id,
												'site_master_id':employee_id2.site_master_id.id,
												'shift':employee_id2.shift_id.id,
												'employee_status':'PH',
												'state':'draft',
												'created': True
												# 'worked_hours':,
												# 'check_in':,
												# 'check_out':,
												# 'in_time':,
												# 'out_time':,
												# 'in_time_updation':,
												# 'out_time_updation':,
												# 'early_leaving':,
												# 'late_coming':,
												# 'import_status':
												# 'reason':
												# 'approve_check':
												# 'remarks':,
											}
							create_id = attendance_obj.create(attendance_vals)
					employee_id2.write({'holiday_ids':[(6,0,to_append)]})
				line2.write({'employee_old_ids':[(6,0,emp_to_compare)]})
				line2.write({'holiday_old_ids':[(6,0,holidays_to_compare)]})
		else:
			raise AccessError("Nothing to assign!")
		return True


