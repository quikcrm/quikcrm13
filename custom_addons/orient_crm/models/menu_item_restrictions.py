# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo import SUPERUSER_ID
from lxml import etree
from odoo.exceptions import UserError


class Partner(models.Model):
    _inherit = ['res.partner']

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(Partner, self).fields_view_get(
            view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        uid = self._context.get('uid')
        doc = etree.XML(res['arch'])
        temp_var = []
        user_data = self.env['res.users'].browse(uid)
        if uid and uid != 1:
            self.env.cr.execute("select name from res_groups where id in (select gid from res_groups_users_rel where uid ="+str(uid)+" and name ilike '%Portal User%')")
            temp_var = self.env.cr.fetchall()
            if temp_var:
                raise UserError(_('Sorry, You are not allowed to access these documents!'))
            # ankit commented
            if user_data.password_reset == False:
                raise UserError(_('YOU HAVE NOT CHANGED YOUR PASSWORD YET ! \n'
                                  'Please click on your username on upper right hand corner, click on "change password" and follow the instructions. You wont be able to continue using the system unless you change your current default password.'))
        return res


class MergePartnerAutomatic(models.TransientModel):
    _inherit = ['base.partner.merge.automatic.wizard']

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(MergePartnerAutomatic, self).fields_view_get(
            view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        uid = self._context.get('uid')
        doc = etree.XML(res['arch'])
        temp_var = []
        user_data = self.env['res.users'].browse(uid)
        if uid and uid != 1:
            self.env.cr.execute("select name from res_groups where id in (select gid from res_groups_users_rel where uid ="+str(uid)+" and name ilike '%Portal User%')")
            temp_var = self.env.cr.fetchall()
            if temp_var:
                raise UserError(_('Sorry, You are not allowed to access these documents!'))
            # ankit commented
            if user_data.password_reset == False:
                raise UserError(_('YOU HAVE NOT CHANGED YOUR PASSWORD YET ! \n'
                                  'Please click on your username on upper right hand corner, click on "change password" and follow the instructions. You wont be able to continue using the system unless you change your current default password.'))
        return res


class ImportPartners(models.Model):
    _inherit = ['import.partners']

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(ImportPartners, self).fields_view_get(
            view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        uid = self._context.get('uid')
        doc = etree.XML(res['arch'])
        temp_var = []
        user_data = self.env['res.users'].browse(uid)
        if uid and uid != 1:
            self.env.cr.execute("select name from res_groups where id in (select gid from res_groups_users_rel where uid ="+str(uid)+" and name ilike '%Portal User%')")
            temp_var = self.env.cr.fetchall()
            if temp_var:
                raise UserError(_('Sorry, You are not allowed to access these documents!'))
            # ankit commented
            if user_data.password_reset == False:
                raise UserError(_('YOU HAVE NOT CHANGED YOUR PASSWORD YET ! \n'
                                  'Please click on your username on upper right hand corner, click on "change password" and follow the instructions. You wont be able to continue using the system unless you change your current default password.'))
        return res


class Lead(models.Model):
    _inherit = ['crm.lead']

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(Lead, self).fields_view_get(
            view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        uid = self._context.get('uid')
        doc = etree.XML(res['arch'])
        temp_var = []
        user_data = self.env['res.users'].browse(uid)
        if uid and uid != 1:
            self.env.cr.execute("select name from res_groups where id in (select gid from res_groups_users_rel where uid ="+str(uid)+" and name ilike '%Portal User%')")
            temp_var = self.env.cr.fetchall()
            if temp_var:
                raise UserError(_('Sorry, You are not allowed to access these documents!'))
            # ankit commented
            if user_data.password_reset == False:
                raise UserError(_('YOU HAVE NOT CHANGED YOUR PASSWORD YET ! \n'
                                  'Please click on your username on upper right hand corner, click on "change password" and follow the instructions. You wont be able to continue using the system unless you change your current default password.'))
        return res
