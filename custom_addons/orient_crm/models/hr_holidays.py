# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo import SUPERUSER_ID
from odoo.exceptions import UserError, AccessError, ValidationError
import datetime
from datetime import datetime, timedelta
from dateutil import *
from dateutil.relativedelta import relativedelta
from odoo.tools import float_compare
import logging
import math
from odoo.tools.translate import _
from odoo.modules.module import get_module_resource
from dateutil.rrule import rrule, DAILY
_logger = logging.getLogger(__name__)
import base64, urllib
import csv
from xlrd import open_workbook
import calendar

HOURS_PER_DAY = 9

class HolidaysType(models.Model):
    _inherit = "hr.holidays.status"

    allocable = fields.Boolean(default=False,string='Allocable ?')
    deductable = fields.Boolean(default=False,string='Deductable ?')
    encashable = fields.Boolean(default=False,string='Encashable ?')
    forwardable = fields.Boolean(default=False,string='Forwardable ?')
    applicable_to = fields.Selection([('confirmed', 'Confirmed Employees'),('all', 'All Employees')], string='Applicable To')
    code = fields.Char('Code', required=True, translate=True)
    half_day = fields.Boolean('Include in half-day leave?')
    sandwich = fields.Boolean('Include in sandwich leaves?')
    # allocation_criteria = fields.Selection([('first_half', 'First-half of the year'),('second_half', 'Second-half of the year')],default=None,track_visibility='onchange',string='Allocation Criteria')
    allocability = fields.Selection([('pro_rata', 'Pro-rata basis'),('all', 'All at once')],default=None,track_visibility='onchange',string='Allocability')
    maximum_allocation = fields.Float('Limit Per Year')
    maximum_limit = fields.Float('Maximum Allocation Value')
    allow_to_override = fields.Boolean('Allow to override?')
    number_of_leaves = fields.Char("Number of Leaves")
    by_data_file = fields.Boolean("By data file?")
    exclude_from_sites = fields.Boolean('Exclude from sites?')


    # @api.onchange('allocability')
    # def onchange_allocability(self):
    #     data = {}
    #     domain = {}
    #     if self.allocability:
    #         if self.allocability == 'all': # all at once
    #             data['allocation_criteria'] = None
    #             data['number_of_leaves'] = '[limit-(months lapsed * (limit/12))]'
    #         else: # pro-rata basis
    #             if not self.allocation_criteria: # no allocation criteria
    #                 data['number_of_leaves'] = '[limit/12]'+'  '+' days per month'
    #             else: # allocation criteria
    #                 data['number_of_leaves'] = '[limit/6]'+'  '+' days per month'
    #     else:
    #         data['number_of_leaves'] = ''
    #     return {'value':data,'domain': domain}


    @api.onchange('allocability')
    def onchange_allocability(self):
        data = {}
        domain = {}
        if self.allocability:
            if self.allocability == 'all': # all at once
                data['number_of_leaves'] = '[limit-(months lapsed * (limit/12))]'
            else: # pro-rata basis
                data['number_of_leaves'] = '[limit/12]'+'  '+' days per month'
        else:
            data['number_of_leaves'] = ''
        return {'value':data,'domain': domain}


    # @api.onchange('allocation_criteria')
    # def onchange_allocation_criteria(self):
    #     data = {}
    #     domain = {}
    #     if self.allocation_criteria:
    #         if self.allocability == 'all': # all at once
    #             data['number_of_leaves'] = '[limit-(months lapsed * (limit/12))]'
    #         else: # pro-rata basis
    #             data['number_of_leaves'] = '[limit/6]'+'  '+' days per month'
    #     else:
    #         if self.allocability:
    #             if self.allocability == 'all': # all at once
    #                 data['number_of_leaves'] = '[limit-(months lapsed * (limit/12))]'
    #             else: # pro-rata basis
    #                 data['number_of_leaves'] = '[limit/12]'+'  '+' days per month'
    #     return {'value':data,'domain': domain}


    @api.multi
    def get_days(self, employee_id):
        # need to use `dict` constructor to create a dict per id
        result = dict((id, dict(max_leaves=0, leaves_taken=0, remaining_leaves=0, virtual_remaining_leaves=0)) for id in self.ids)
        holidays = self.env['hr.holidays'].search([
            ('employee_id', '=', employee_id),
            ('state', 'in', ['confirm', 'validate1', 'validate','allocated']),
            ('holiday_status_id', 'in', self.ids)
        ])
        for holiday in holidays:
            status_dict = result[holiday.holiday_status_id.id]
            if holiday.type == 'add':
                if holiday.state == 'validate' or holiday.state == 'allocated':
                    # note: add only validated allocation even for the virtual
                    # count; otherwise pending then refused allocation allow
                    # the employee to create more leaves than possible
                    status_dict['virtual_remaining_leaves'] += holiday.total_days
                    status_dict['max_leaves'] += holiday.total_days
                    status_dict['remaining_leaves'] += holiday.total_days
            elif holiday.type == 'remove':  # number of days is negative
                status_dict['virtual_remaining_leaves'] -= holiday.total_days
                if holiday.state == 'validate' or holiday.state == 'allocated':
                    status_dict['leaves_taken'] += holiday.total_days
                    status_dict['remaining_leaves'] -= holiday.total_days
        return result

    @api.multi
    def name_get(self):
        sandwich_ids = self.search([('sandwich','=',True)]).ids
        if sandwich_ids == self.ids:
            print("in sandwich ids--------------------")
            res = []
            for record in self:
                name = record.name
                if record.allocable == True:
                    name = "%(name)s (%(count)s)" % {
                        'name': name,
                        'count': _('%g remaining out of %g') % (record.virtual_remaining_leaves or 0.0, record.max_leaves or 0.0)
                    }
                res.append((record.id, name))
            return res
        if self._context.get('type') and self._context.get('type') == 'add':
            print("in allocation mode--------------------")
            allocable_ids = self.search([('allocable','=',True)])
            res = []
            for record in allocable_ids:
                name = record.name
                res.append((record.id, name))
            return res
        if not self._context.get('request_type') and self._context.get('type') and self._context.get('type') == 'remove':
            print("in leave application-------------------")
            # case: if half day is selected
            if self._context.get('half_day_applicable'):
                half_day_ids = self.search([('half_day','=',True)])
                search_ids = half_day_ids
            # half day not selected
            else:
                search_domain = [('code','!=','OD')]
                user_data = self.env['res.users'].browse(self.env.uid)
                emp_id = self.env['hr.employee'].search([('emp_code','=',user_data.login)])
                if emp_id and emp_id.site_master_id:
                    # if site is not a branch
                    if emp_id.site_master_id.is_a_branch == False:
                        search_domain.append(('exclude_from_sites','=',False))
                no_od_ids = self.search(search_domain)
                search_ids = no_od_ids
            res = []
            for record in search_ids:
                name = record.name
                if self._context.get('state') and self._context.get('state') == 'draft':
                    if record.allocable == True:
                        name = "%(name)s (%(count)s)" % {
                            'name': name,
                            'count': _('%g remaining out of %g') % (record.virtual_remaining_leaves or 0.0, record.max_leaves or 0.0)
                        }
                res.append((record.id, name))
            return res
        res = []
        for record in self:
            print("no where---------------------")
            name = record.name
            if self._context.get('state') and self._context.get('state') == 'draft':
                if record.allocable == True:
                    name = "%(name)s (%(count)s)" % {
                        'name': name,
                        'count': _('%g remaining out of %g') % (record.virtual_remaining_leaves or 0.0, record.max_leaves or 0.0)
                    }
            res.append((record.id, name))
        return res

    # @api.model
    # def name_search(self, name, args=None, operator='ilike', limit=100):
    #     args = args or []
    #     domain = []
    #     if self.allocable:
    #         domain = [('allocable', '=', True)]
    #     else:
    #         domain = []
    #     holiday_status = self.search(domain + args, limit=limit)
    #     return holiday_status.name_get()


class Holidays(models.Model):
    _inherit = "hr.holidays"
    _order = "type desc, date_from_new desc"


    def _default_employee(self):
        if self.env.context.get('default_type') == 'add':
            return None
        else:
            return self.env.context.get('default_employee_id') or self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)


    def _default_leave_manager_id(self):
        users = []
        user_id = None
        # category_id = self.env['ir.module.category'].search([('name','=','Leaves')])
        # leave_manager_group = self.env['res.groups'].search([('category_id','=',category_id.id),('name','=','Manager')])
        query = """SELECT id FROM ir_module_category WHERE name = 'Leaves';"""
        self.env.cr.execute(query)
        category_id = self.env.cr.dictfetchall()
        leave_manager_group = self.env['res.groups'].search([('category_id','=',category_id[0].get('id')),('name','=','Manager')])
        for user in leave_manager_group.users:
            if user.id != 1:
                users.append(user.id)
        if users:
            user_id = users[0]
        return user_id


    def _default_request_type(self):
        if self.env.context.get('od_req'):
            if self.env.context.get('od_req') == True:
                return 'od'
            else:
                return 'leave'
        else:
            return None


    def _default_holidays_status_id(self):
        if self.env.context.get('od_req'):
            if self.env.context.get('od_req') == True:
                od_id = self.env['hr.holidays.status'].search([('code', '=', 'OD')], limit=1)
                return self.env['hr.holidays.status'].search([('code', '=', 'OD')], limit=1)
            else:
                return None
        else:
            return None


    def _default_code(self):
        if self.env.context.get('od_req'):
            if self.env.context.get('od_req') == True:
                return 'OD'
            else:
                return None
        else:
            return None

    # def _get_manager_id(self):
        # HR manager ID email
        # hr_position = self.env['hr.job'].search([('hr_manager_bool', '=', True)], limit=1)
        # employee_manager = self.env['hr.employee'].search([('job_id', '=',hr_position.id)], limit=1)
        # return employee_manager.id
        # return 17487


    def _default_name(self):
        if self.env.context.get('default_type') == 'add':
            return "Leave Allocation"
        else:
            return None

    def _default_current_month(self):
        month = datetime.today().month
        if month == 1:
            current_month = 'jan'
        if month == 2:
            current_month = 'feb'
        if month == 3:
            current_month = 'mar'
        if month == 4:
            current_month = 'apr'
        if month == 5:
            current_month = 'may'
        if month == 6:
            current_month = 'june'
        if month == 7:
            current_month = 'july'
        if month == 8:
            current_month = 'aug'
        if month == 9:
            current_month = 'sept'
        if month == 10:
            current_month = 'oct'
        if month == 11:
            current_month = 'nov'
        if month == 12:
            current_month = 'dec'
        return current_month

    def _default_financial_year(self):
        financial_year_id = False
        curr_date = datetime.today()
        year = curr_date.year
        year_master_ids = self.env['year.master'].search([('name','ilike',year)])
        for each_year_master_id in year_master_ids:
            start_date = datetime.strptime(each_year_master_id.start_date,'%Y-%m-%d')
            end_date = datetime.strptime(each_year_master_id.end_date,'%Y-%m-%d')
            if curr_date >= start_date and curr_date <= end_date:
                financial_year_id = each_year_master_id
        if not financial_year_id:
            raise AccessError("Financial Year is not defined")
        return financial_year_id

    def _default_pl_count(self):
        employee_id = self.env.context.get('default_employee_id') or self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        financial_year_id = False
        curr_date = datetime.today()
        year = curr_date.year
        year_master_ids = self.env['year.master'].search([('name','ilike',year)])
        for each_year_master_id in year_master_ids:
            start_date = datetime.strptime(each_year_master_id.start_date,'%Y-%m-%d')
            end_date = datetime.strptime(each_year_master_id.end_date,'%Y-%m-%d')
            if curr_date >= start_date and curr_date <= end_date:
                financial_year_id = each_year_master_id
        if not financial_year_id:
            raise AccessError("Financial Year is not defined!")
        allocated_pl_ids = self.search([('type','=','add'),('code','=','PL'),('employee_id','=',employee_id.id)])
        balanced_days = 0.0
        for each_pl_id in allocated_pl_ids:
            balanced_days = balanced_days+each_pl_id.balanced_days
        return balanced_days

    def _default_slcl_count(self):
        employee_id = self.env.context.get('default_employee_id') or self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        financial_year_id = False
        curr_date = datetime.today()
        year = curr_date.year
        year_master_ids = self.env['year.master'].search([('name','ilike',year)])
        for each_year_master_id in year_master_ids:
            start_date = datetime.strptime(each_year_master_id.start_date,'%Y-%m-%d')
            end_date = datetime.strptime(each_year_master_id.end_date,'%Y-%m-%d')
            if curr_date >= start_date and curr_date <= end_date:
                financial_year_id = each_year_master_id
        if not financial_year_id:
            raise AccessError("Financial Year not defined!")
        allocated_slcl_ids = self.search([('type','=','add'),('code','=','SL/CL'),('employee_id','=',employee_id.id)])
        balanced_days = 0.0
        for each_slcl_id in allocated_slcl_ids:
            balanced_days = balanced_days+each_slcl_id.balanced_days
        return balanced_days


    # manager_id = fields.Many2one('hr.employee', string='Reporting Manager')
    # leave_type = fields.Selection([('pr_l','Privilege Leave'),('cas_l','Casual Leave'),('sl','Sick Leave'),
    #                                 ('out_l','Outdoor Leave'),('sol','Short Outdoor Leave'),
    #                                 ('co','Comp Off'),('pa_l','Paternity Leave'),('mat_l','Maternity Leave'),
    #                                 ('mar_l','Marriage Leave'),('lwp','Leave Without Pay')], string="Leave Type")

    manager_id = fields.Many2one('hr.employee', string='Manager', readonly=False)
    user_id = fields.Many2one('res.users', string='User', related='employee_id.user_id', related_sudo=True, store=True, readonly=False)
    # user_id = fields.Many2one('res.users', string='User', related='employee_id.user_id', related_sudo=True, store=True, readonly=True)
    # default=lambda self: self.env.uid,
    department_id = fields.Many2one('hr.department', string='Department', readonly=False)
    first_approver_id = fields.Many2one('hr.employee', string='First Approval', readonly=False, copy=False,
        help='This area is automatically filled by the user who validate the leave', oldname='manager_id')
    name = fields.Char('Description',default=_default_name)
    holiday_status_od_id = fields.Many2one("hr.holidays.status", string="Leave Type OD",readonly=True, default=_default_holidays_status_id)
    manager_user_id = fields.Many2one('res.users', string='Manager User')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('cancel', 'Cancelled'),
        ('confirm', 'Applied'),
        ('refuse', 'Refused'),
        ('validate1', 'Second Approval'),
        ('validate', 'Approved'),
        ('allocated', 'Allocated'),
        ], string='Status', readonly=False, track_visibility='onchange', copy=False, default='draft',
            help="The status is set to 'Draft', when a leave request is created." +
            "\nThe status is 'Applied', when leave request is applied by user." +
            "\nThe status is 'Refused', when leave request is refused by manager." +
            "\nThe status is 'Approved', when leave request is approved by manager.")
    approved_by = fields.Many2one('hr.employee', string='Approved By')
    check_user = fields.Boolean('Check User', compute='get_user')
    date_from_new = fields.Date('From', readonly=True, index=True, copy=False,
        states={'draft': [('readonly', False)], 'confirm': [('readonly', False)]}, track_visibility='onchange')
    date_to_new = fields.Date('To', readonly=True, copy=False,
        states={'draft': [('readonly', False)], 'confirm': [('readonly', False)]}, track_visibility='onchange')
    total_days = fields.Float(
        'Duration', copy=False, readonly=True,
        states={'draft': [('readonly', False)], 'confirm': [('readonly', False)]},
        help='Number of days of the leave request according to your working schedule.')
    balanced_days = fields.Float('BalancedDays', copy=False, readonly=False)
    employee_id = fields.Many2one('hr.employee', string='Employee', index=True, readonly=True,
        states={'draft': [('readonly', False)], 'confirm': [('readonly', False)]}, default=_default_employee, track_visibility='onchange')
    code = fields.Char('Code', translate=True, track_visibility='onchange',default=_default_code)
    employee_code = fields.Integer('Employee Code')
    allocated = fields.Boolean('Allocated', default=False)
    half_day_applicable = fields.Boolean('Need to apply for half day leave?',track_visibility='onchange')
    comp_off = fields.Boolean('Comp Off')
    comp_off_date = fields.Date('Comp Off Date')
    current_month = fields.Selection([
        ('jan', 'January'),
        ('feb', 'February'),
        ('mar', 'March'),
        ('apr', 'April'),
        ('may', 'May'),
        ('june', 'June'),
        ('july', 'July'),
        ('aug', 'August'),
        ('sept', 'September'),
        ('oct', 'October'),
        ('nov', 'November'),
        ('dec', 'December')
        ], string='Month',default=_default_current_month)
    financial_year_id = fields.Many2one('year.master', string='Financial Year',default=_default_financial_year)
    refused_by = fields.Many2one('hr.employee', string='Rejected By')
    leave_manager_id = fields.Many2one('res.users', string='Leave Manager', default=_default_leave_manager_id)
    sandwich = fields.Boolean('Sandwich?', default=False, track_visibility='onchange')
    hr_manager_id = fields.Many2one('hr.employee', string='HR Manager')
    no_action = fields.Boolean('No Action', compute='_compute_no_action')
    hide_comments = fields.Boolean('Hide comments', default=True, compute='_compute_hide_comments')
    request_type = fields.Selection([('leave', 'Leave'),('od', 'OD')],string='Request Type OD',default=_default_request_type)
    half_day_presence = fields.Selection([('first', 'First Half'),('second', 'Second Half')],string='Presence')
    pl_count = fields.Float('PL Balance', default=_default_pl_count)
    slcl_count = fields.Float('SL/CL Balance', default=_default_slcl_count)
    holiday_allocation_id = fields.Many2one('holiday.allocation', string='Allocation Master')
    holiday_allocation_temp_id = fields.Many2one('holiday.allocation', string='Allocation Master')
    to_be_encashed = fields.Float('To be encashed')
    half_od_applicable = fields.Boolean('Need to apply for half OD?',track_visibility='onchange')
    half_od_presence = fields.Selection([('first', 'First Half'),('second', 'Second Half')],string='Presence')
    site_id = fields.Many2one('site.master', string='Site')



    @api.multi
    def _compute_no_action(self):
        """ HR Executives and HR manager can approve the leave request. User cannot approve his own leave request """
        current_user = self.env.user
        group_hr_manager = self.env.ref('hr_holidays.group_hr_holidays_manager')
        if self.employee_id.user_id.id == current_user.id:
            if group_hr_manager not in current_user.groups_id:
                self.no_action = True


    @api.multi
    def _compute_hide_comments(self):
        """ HR Executives and HR manager can approve the leave request. User cannot approve his own leave request """
        current_user = self.env.user
        group_hr_manager = self.env.ref('hr_holidays.group_hr_holidays_manager')
        group_hr_officer = self.env.ref('hr_holidays.group_hr_holidays_user')
        group_hr_reporting_manager = self.env.ref('orient_leave_management.group_hr_holidays_reporting')
        # print("group_hr_manager",group_hr_manager)
        # print("group_hr_officer",group_hr_officer)
        # print("group_hr_reporting_manager",group_hr_reporting_manager)
        # print("current_user.groups_id------------------",current_user.groups_id)
        # hide_comments = False
        # only employee rights
        if group_hr_reporting_manager not in current_user.groups_id and group_hr_officer not in current_user.groups_id and group_hr_manager not in current_user.groups_id:
            # print("only employee-------")
            if self.state != 'refuse':
                hide_comments = True
            else:
                hide_comments = False
        # reporting manager_id
        elif group_hr_reporting_manager in current_user.groups_id:
            # print("reporting manager--------")
            # other user's leaves
            if self.employee_id.user_id.id != current_user.id: 
                hide_comments = False 
            # reporting manager own leaves
            else:
                if self.state == 'refuse':  
                    hide_comments = False
                else:
                    hide_comments = True
        # hr officer
        elif group_hr_officer in current_user.groups_id:
            # print("officer----------")
            # other user's leaves
            if self.employee_id.user_id.id != current_user.id: 
                if self.state not in ['confirm','refuse']: 
                    hide_comments = True 
                else:
                    hide_comments = False
            # hr officer own leaves
            else:
                if self.state == 'refuse':  
                    hide_comments = False
                else:
                    hide_comments = True
        # hr manager
        if group_hr_manager in current_user.groups_id:
            # print("manager----------")
            # other user's leaves
            hide_comments = False 
            # if self.employee_id.user_id.id != current_user.id: 
            #     if self.state not in ['confirm','refuse']: 
            #         self.hide_comments = True 
            # # hr manager own leaves
            # else:
            #     if self.state not in ['confirm','refuse']:  
            #         self.hide_comments = True
        # print("hide_comments",hide_comments)
        self.hide_comments = hide_comments

    # @api.multi
    # def _compute_hide_comments(self):
    #     """ HR Executives and HR manager can approve the leave request. User cannot approve his own leave request """
    #     current_user = self.env.user
    #     group_hr_manager = self.env.ref('hr_holidays.group_hr_holidays_manager')
    #     group_hr_officer = self.env.ref('hr_holidays.group_hr_holidays_user')
    #     group_hr_reporting_manager = self.env.ref('orient_leave_management.group_hr_holidays_reporting')
    #     # only employee rights
    #     if group_hr_reporting_manager not in current_user.groups_id and group_hr_officer not in current_user.groups_id and group_hr_manager not in current_user.groups_id:
    #         if self.state != 'refuse':
    #             self.hide_comments = True
    #     # reporting manager_id
    #     if group_hr_reporting_manager in current_user.groups_id and group_hr_officer not in current_user.groups_id and group_hr_manager not in current_user.groups_id:
    #         # other user's leaves
    #         if self.employee_id.user_id.id != current_user.id: 
    #             if self.state not in ['confirm','refuse']: 
    #                 self.hide_comments = True 
    #         # reporting manager own leaves
    #         else:
    #             if self.state not in ['confirm','refuse']:  
    #                 self.hide_comments = True
    #     # hr officer
    #     if group_hr_reporting_manager not in current_user.groups_id and group_hr_officer in current_user.groups_id and group_hr_manager not in current_user.groups_id:
    #         # other user's leaves
    #         if self.employee_id.user_id.id != current_user.id: 
    #             if self.state not in ['confirm','refuse']: 
    #                 self.hide_comments = True 
    #         # hr officer own leaves
    #         else:
    #             if self.state not in ['confirm','refuse']:  
    #                 self.hide_comments = True


    @api.multi
    def _compute_can_reset(self):
        """ User can reset a leave request if it is its own leave request
        """
        user = self.env.user
        group_hr_manager = self.env.ref('hr_holidays.group_hr_holidays_manager')
        group_hr_officer = self.env.ref('hr_holidays.group_hr_holidays_user')
        group_reporting_manager = self.env.ref('orient_leave_management.group_hr_holidays_reporting')
        for holiday in self:
            # if group_hr_manager in user.groups_id or holiday.employee_id and holiday.employee_id.user_id == user:
            # if group_hr_manager not in user.groups_id and group_hr_officer not in user.groups_id and group_reporting_manager not in user.groups_id:
            if holiday.employee_id.user_id and holiday.employee_id.user_id.id == user.id:
                holiday.can_reset = True


    # @api.onchange('request_type')
    # def onchange_request_type(self):
    #     domain = {}
    #     data = {}
    #     if self.request_type == 'od':
    #         domain = {'holiday_status_id': [('code','=','OD')]}
    #     else:
    #         domain = {'holiday_status_id': []}
    #     return {'domain':domain,'value':data}



    @api.onchange('half_day_applicable')
    def onchange_half_day_applicable(self):
        domain = {}
        data = {}
        if self.half_day_applicable:
            domain = {'holiday_status_id': [('half_day','=',True)]}
            data['total_days'] = 0.5
        else:
            domain = {'holiday_status_id': []}
            if self.date_from_new and self.date_to_new:
                dfn = datetime.strptime(self.date_from_new, '%Y-%m-%d')
                dtn = datetime.strptime(self.date_to_new, '%Y-%m-%d')
                difference = abs((dfn - dtn).days) + 1
                data['total_days'] = difference
                data['number_of_days_temp'] = difference
            else:
                data['total_days'] = 0
                data['number_of_days_temp'] = 0
        data['holiday_status_id'] = False
        return {'domain':domain,'value':data}



    @api.onchange('half_od_applicable')
    def onchange_half_od_applicable(self):
        domain = {}
        data = {}
        if self.half_od_applicable:
            data['total_days'] = 0.5
        else:
            if self.date_from_new and self.date_to_new:
                dfn = datetime.strptime(self.date_from_new, '%Y-%m-%d')
                dtn = datetime.strptime(self.date_to_new, '%Y-%m-%d')
                difference = abs((dfn - dtn).days) + 1
                data['total_days'] = difference
                data['number_of_days_temp'] = difference
            else:
                data['total_days'] = 0
                data['number_of_days_temp'] = 0
        return {'value':data}



    @api.onchange('sandwich')
    def onchange_sandwich(self):
        domain = {}
        data = {}
        if self.sandwich:
            domain = {'holiday_status_id': [('sandwich','=',True)]}
        else:
            domain = {'holiday_status_id': []}
        return {'domain':domain,'value':data}
        

    @api.onchange('holiday_status_id')
    def onchange_code(self):
        data = {}
        holiday_stat_id = self.env['hr.holidays.status'].search([('code','=','CO')])
        if self.holiday_status_id.name==holiday_stat_id.name:
            data['comp_off'] = True
        else:
            data['comp_off'] = False
        if self.holiday_status_id:
            data['code'] = self.holiday_status_id.code
        else:
            data['code'] = None
        if self.holiday_status_id == holiday_stat_id and self.type=='add':
            data['total_days'] = 1
        return {'value':data}

    @api.onchange('date_from_new')
    def onchange_date_from_new(self):
        data = {}
        age = 0
        difference = 0
        if self.date_from_new and self.request_type == 'od':
            data['holiday_status_id'] = self.holiday_status_od_id.id
            data['code'] = 'OD'
        if self.date_from_new and self.date_to_new:
            if self.code != 'OD':
                if not self.half_day_applicable:
                    dfn = datetime.strptime(self.date_from_new, '%Y-%m-%d')
                    dtn = datetime.strptime(self.date_to_new, '%Y-%m-%d')
                    difference = abs((dfn - dtn).days) + 1
                    data['total_days'] = difference
                    data['number_of_days_temp'] = difference
                    if difference == 1:
                        data['number_of_days'] = -difference
            else:
                if not self.half_od_applicable:
                    dfn = datetime.strptime(self.date_from_new, '%Y-%m-%d')
                    dtn = datetime.strptime(self.date_to_new, '%Y-%m-%d')
                    difference = abs((dfn - dtn).days) + 1
                    data['total_days'] = difference
                    data['number_of_days_temp'] = difference
                    if difference == 1:
                        data['number_of_days'] = -difference
        else:
            data['total_days'] = difference
            data['number_of_days_temp'] = difference
        return {'value':data}

    @api.onchange('date_to_new')
    def onchange_date_to_new(self):
        data = {}
        age = 0
        difference = 0
        if self.date_from_new and self.date_to_new:
            if self.code != 'OD':
                if not self.half_day_applicable:
                    dfn = datetime.strptime(self.date_from_new, '%Y-%m-%d')
                    dtn = datetime.strptime(self.date_to_new, '%Y-%m-%d')
                    difference = abs((dfn - dtn).days) + 1
                    data['total_days'] = difference
                    data['number_of_days_temp'] = difference
                    if difference == 1:
                        data['number_of_days'] = -difference
                else:
                    data['total_days'] = 0.5
                    data['number_of_days_temp'] = 0.5
            else:
                if not self.half_od_applicable:
                    dfn = datetime.strptime(self.date_from_new, '%Y-%m-%d')
                    dtn = datetime.strptime(self.date_to_new, '%Y-%m-%d')
                    difference = abs((dfn - dtn).days) + 1
                    data['total_days'] = difference
                    data['number_of_days_temp'] = difference
                    if difference == 1:
                        data['number_of_days'] = -difference
                else:
                    data['total_days'] = 0.5
                    data['number_of_days_temp'] = 0.5
        else:
            data['total_days'] = difference
            data['number_of_days_temp'] = difference
        return {'value':data}

    @api.onchange('holiday_type')
    def _onchange_type(self):
        if self.holiday_type == 'employee' and not self.employee_id:
            if self.env.context.get('default_type') == 'add':
                self.employee_id = None
            else:
                self.employee_id = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        elif self.holiday_type != 'employee':
            self.employee_id = None


    @api.constrains('date_from_new', 'date_to_new')
    def _check_date(self):
        for holiday in self:
            domain = [
                ('date_from_new', '<=', holiday.date_from_new),
                ('date_to_new', '>=', holiday.date_to_new),
                ('employee_id', '=', holiday.employee_id.id),
                ('id', '!=', holiday.id),
                ('type', '=', holiday.type),
                ('state', 'not in', ['cancel','refuse','draft']),
            ]
            existing_holiday = self.search(domain)
            print("existing_holiday",existing_holiday)
            if existing_holiday.half_day_applicable or existing_holiday.half_od_applicable: 
                if holiday.half_day_presence or holiday.half_od_applicable:
                    if existing_holiday.code == holiday.code:
                        raise ValidationError(_('Not applicable!'))
                    else:
                        if existing_holiday.half_day_presence == holiday.half_od_presence:
                            raise ValidationError(_('You can not have 2 leaves that overlap on same day!'))
                        else:
                            pass
                else:
                    raise ValidationError(_('You can not have 2 leaves that overlap on same day!'))

                # if existing_holiday.half_day_applicable == True and holiday.half_day_applicable == True:
                #     if existing_holiday.half_day_presence == self.half_day_presence:
                #         raise ValidationError(_('You can not have 2 leaves that overlap on same day & time!'))
                # elif existing_holiday.half_od_applicable == True and holiday.half_od_applicable == True:
                #     raise ValidationError(_('You already have applied for half OD for the given date!'))
                # elif existing_holiday.half_day_applicable == True and holiday.half_od_applicable == False:
                #     raise ValidationError(_('You can not have 2 leaves that overlap on same day!'))
                # elif existing_holiday.code == 'OD' and holiday.half_day_applicable != True:
                #     raise ValidationError(_('You can not have 2 leaves that overlap on same day!'))
                # else:
                #     pass
            else:
                nholidays = self.search_count(domain)
                if nholidays:
                    raise ValidationError(_('You can not have 2 leaves that overlap on same day!'))


    @api.constrains('state', 'total_days', 'holiday_status_id')
    def _check_holidays(self):
        for holiday in self:
            if holiday.holiday_type != 'employee' or holiday.type != 'remove' or not holiday.employee_id or holiday.holiday_status_id.limit:
                continue
            leave_days = holiday.holiday_status_id.get_days(holiday.employee_id.id)[holiday.holiday_status_id.id]
            if holiday.holiday_status_id.allocable:
                if float_compare(leave_days['remaining_leaves'], 0, precision_digits=2) == -1 or \
                  float_compare(leave_days['virtual_remaining_leaves'], 0, precision_digits=2) == -1:
                    raise ValidationError(_('The number of remaining leaves is not sufficient for this leave type.\n'
                                            'Please verify also the leaves waiting for validation.'))

    @api.constrains('total_days')
    def _total_days_check(self):
        for holiday in self:
            if holiday.total_days == 0:
                raise UserError(_('Leaves cannot be applied for 0 days!'))
        if self.code == 'SL/CL':
            if self.total_days > self.holiday_status_id.maximum_allocation:
                raise UserError(_('Limit for %s is %s !') % (self.code,self.holiday_status_id.maximum_allocation))
            existing_slcl_id = self.search([('employee_id', '=', self.employee_id.id),('type', '=', 'add'),('code', '=', 'SL/CL'),('allocated', '=', True),('id', '!=', self.id)])
            if existing_slcl_id:
                slcl_to_allocate = existing_slcl_id.total_days + self.total_days
                if slcl_to_allocate > self.holiday_status_id.maximum_allocation:
                    raise UserError(_('Limit for %s is %s !') % (self.code,self.holiday_status_id.maximum_allocation))
        if self.code == 'PL':
            if self.holiday_status_id.allow_to_override == False:
                if self.total_days > self.holiday_status_id.maximum_limit:
                    raise UserError(_('Limit for %s is %s !') % (self.code,self.holiday_status_id.maximum_limit))
                existing_pl_id = self.search([('employee_id', '=', self.employee_id.id),('type', '=', 'add'),('code', '=', 'PL'),('allocated', '=', True),('id', '!=', self.id)])
                if existing_pl_id:
                    existing_pl_id = existing_pl_id.total_days + self.total_days
                    if slcl_to_allocate > self.holiday_status_id.maximum_limit:
                        raise UserError(_('Limit for %s is %s !') % (self.code,self.holiday_status_id.maximum_limit))


    @api.constrains('type')
    def _allocation_repeat(self):
        if self.type == 'add':
            existing_allocated_id = self.search([('employee_id', '=', self.employee_id.id),('type', '=', 'add'),('code', '=', self.code),('allocated', '=', True),('id', '!=', self.id)])
            if self.code != 'CO':
                if existing_allocated_id and existing_allocated_id.id!=self.id:
                    raise UserError(_('%s are already allocated to employee %s. Please click on "Update Leaves" to manipulate the leave values!') % (self.code,self.employee_id.name))
            

    _sql_constraints = [
        ('type_value_new', "CHECK( (holiday_type='employee' AND employee_id IS NOT NULL) or (holiday_type='category' AND category_id IS NOT NULL))",
         "The employee or employee category of this request is missing. Please make sure that your user login is linked to an employee."),
        ('date_check2_new', "CHECK ( (type='add') OR (date_from_new <= date_to_new))", "The start date must be anterior to the end date."),
    ]


    @api.multi
    def name_get(self):
        res = []
        for leave in self:
            if leave.type == 'remove':
                if self.env.context.get('short_name'):
                    res.append((leave.id, _("%s : %.2f day(s)") % (leave.name or leave.holiday_status_id.name, leave.total_days)))
                else:
                    res.append((leave.id, _("%s : %.2f day(s)") % (leave.holiday_status_id.name, leave.total_days)))
            else:
                res.append((leave.id, _("Allocation of %s : %.2f day(s) To %s") % (leave.holiday_status_id.name, leave.total_days, leave.employee_id.name)))
        return res

    def get_user(self):
        for each in self:
            record_user = each.employee_id.user_id.id
            logged_in_user_id = self.env['res.users'].search([('id', '=', each._uid)])
            if logged_in_user_id.has_group('hr.group_hr_manager') or logged_in_user_id.has_group('hr.group_hr_user') or logged_in_user_id.has_group('orient_hr_resignation.group_reporting_manager'):
                if record_user == logged_in_user_id.id:
                    each.check_user = True
                else:
                    if each.employee_id.parent_id.user_id.id == logged_in_user_id.id or each.employee_id.parent_id.parent_id.user_id.id == logged_in_user_id.id:
                        each.check_user = True
                    else:
                        each.check_user = False
            else:
                each.check_user = False


    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        self.employee_code = self.employee_id.emp_code
        self.manager_id = self.employee_id and self.employee_id.parent_id
        self.department_id = self.employee_id.department_id
        self.manager_user_id = self.employee_id.parent_id.user_id
        self.site_id = self.employee_id.site_master_id
        # self.user_id = self.employee_id.user_id

    @api.multi
    def action_draft(self):
        for holiday in self:
            if not holiday.can_reset:
                raise UserError(_('Only an HR Manager or the concerned employee can reset to draft.'))
            if holiday.state not in ['confirm', 'refuse']:
                raise UserError(_('Leave request state must be "Rejected" or "Applied" in order to reset to Draft.'))
            if holiday.sandwich == True:
                raise UserError(_('Sandwiched leaves cannot be Cancelled. Please contact system admin or ask the manager to reject in order to re-apply.'))
            holiday.write({
                'state': 'draft',
                'first_approver_id': False,
                'second_approver_id': False,
            })
            if self.code == 'CO':
                allocated_leave_id = self.search([('employee_id', '=', self.employee_id.id),('type', '=', 'add'),('code', '=', self.code),('comp_off_date', '=', self.comp_off_date)])
            else:
                allocated_leave_id = self.search([('employee_id', '=', self.employee_id.id),('type', '=', 'add'),('code', '=', self.code)])
            if allocated_leave_id:
                balanced_days = allocated_leave_id.balanced_days+self.total_days
                # allocated_leave_id.write({'balanced_days':balanced_days})
                self.env.cr.execute("update hr_holidays set balanced_days=%s where id=%s" %(balanced_days,str(allocated_leave_id.id)))
            linked_requests = holiday.mapped('linked_request_ids')
            for linked_request in linked_requests:
                linked_request.action_draft()
            linked_requests.unlink()
        template_id = self.env.ref('orient_leave_management.email_template_for_leavesreset', False)
        self.env['mail.template'].browse(template_id.id).send_mail(self.id, force_send=True)
        return True


    @api.multi
    def daterange(start_date, end_date):
        for n in range(int ((end_date - start_date).days)):
            yield start_date + timedelta(n)


    @api.multi
    def action_confirm(self):
        hr_position = self.env['hr.job'].search([('hr_manager_bool', '=', True)], limit=1)
        if hr_position:
            employee_manager = self.env['hr.employee'].search([('job_id', '=',hr_position.id)], limit=1)
            if employee_manager:
                self.hr_manager_id = employee_manager.id

        # check if applicable status and employee's position match-------------------------------------------------------------------
        if self.holiday_status_id.applicable_to == 'confirmed':
            if self.employee_id.position_type == 'probation':
                raise AccessError(_('Sorry ! %s are applicable only for confirmed employees.') % (self.holiday_status_id.name))
        #----------------------------------------------------------------------------------------------------------------------------

        if self.date_from_new and self.date_to_new:
            attendance_obj = self.env['hr.attendance']
            holiday_obj = self.env['holiday.master']
            employee_id = self.employee_id.id
            code = self.code
            no_of_days = self.total_days
            dfn = datetime.strptime(self.date_from_new, '%Y-%m-%d')
            dtn = datetime.strptime(self.date_to_new, '%Y-%m-%d')
            date_list = []
            holidays = []
            worked_day_id = False
            for dt in rrule(DAILY, dtstart=dfn, until=dtn):
                holidays.append(dt.weekday())
                date_list.append(datetime.strftime(dt,"%Y-%m-%d"))

            # current_year = datetime.strptime(str(datetime.now().date()), "%Y-%m-%d").year
            # current_month = datetime.strptime(str(datetime.now().date()), "%Y-%m-%d").month
            # for date_rec in date_list:
            #     date_year = datetime.strptime(date_rec, "%Y-%m-%d").year
            #     date_month = datetime.strptime(date_rec, "%Y-%m-%d").month
            #     if (date_year == current_year) and (date_month < current_month):
            #         raise UserError(_('Sorry. you cannot apply for a backdated leave!!'))
            #     if (date_year < current_year):
            #         raise UserError(_('Sorry. you cannot apply for a backdated leave!!'))

            # check if user is already present for the selected duration--------------------------------------------------------------
            # restrictions on OD
            if self.code != 'OD':
                if self.half_day_applicable == False:
                    for date_list_item in date_list:
                        worked_date = datetime.strptime(date_list_item, '%Y-%m-%d').date()
                        worked_day_id = self.env['hr.attendance'].search([('employee_id','=',self.employee_id.id),('attendance_date','=',worked_date),('worked_hours','>=',4.3)],limit=1)
                    if worked_day_id:
                        raise UserError(_('Sorry. Cannot apply for a leave since you were present in the selected duration !'))
            else:
                leave_date = str(dfn)[:10]
                attendance_id = attendance_obj.search([('employee_id','=',employee_id),('attendance_date','=',leave_date)])
                if no_of_days == 1.0:
                    if attendance_id:
                        if attendance_id.employee_status == 'AB':
                            pass
                        elif attendance_id.employee_status == '' or attendance_id.employee_status == ' ':
                            pass
                        else:
                            raise UserError(_('Not applicable!'))
                    else:
                        pass
                if no_of_days == 0.5:
                    if attendance_id:
                        if attendance_id.employee_status == 'AB':
                            pass
                        elif attendance_id.employee_status == 'half_day_p_ab':
                            pass
                        elif attendance_id.employee_status == '' or attendance_id.employee_status == ' ':
                            pass
                        else:
                            raise UserError(_('Not applicable!'))
                    else:
                        pass
            #------------------------------------------------------------------------------------------------------------------------


            # Backdated leaves logic-------------------------------------------------------------------------------------------------
            date_to_month = datetime.strptime(self.date_to_new, "%Y-%m-%d").strftime('%B')
            curr_date = datetime.today().strftime('%Y-%m-%d')
            curr_month = datetime.strptime(curr_date,"%Y-%m-%d").strftime('%B')
            # check if holiday application date is not greater than current date to check backdated leaves logic
            curr_day =  datetime.today().strftime("%d")
            if dtn < datetime.today():
                if date_to_month != curr_month:
                    if int(curr_day) > 5:
                        raise UserError(_('Sorry. Time to apply for this leave has lapsed!'))
            #------------------------------------------------------------------------------------------------------------------------



            #Materinity leave logic-------------------------------------------------------------------------------------------------
            if self.code == 'ML':
                total_maternity_leave_days = 0
                maternity_leave_ids = self.search([('employee_id','=',self.employee_id.id),('code','=','ML'),('state','in',['confirm','validate']),('financial_year_id','=',self.financial_year_id.id)])
                if maternity_leave_ids:
                    existing_maternity_leave_days = 0
                    for each_maternity_leave_id in maternity_leave_ids:
                        existing_maternity_leave_days = existing_maternity_leave_days + each_maternity_leave_id.total_days
                    total_maternity_leave_days = existing_maternity_leave_days +self.total_days
                    if total_maternity_leave_days > self.holiday_status_id.maximum_allocation:
                        raise UserError(_('Exceeding Limit! Maximum limit for %s is %s.') % (self.holiday_status_id.name,self.holiday_status_id.maximum_allocation))
                else:
                    if self.total_days > self.holiday_status_id.maximum_allocation:
                        raise UserError(_('Exceeding Limit! Maximum limit for %s is %s.') % (self.holiday_status_id.name,self.holiday_status_id.maximum_allocation))
            #---------------------------------------------------------------------------------------------------------------------------            

            #Paternity leave logic-------------------------------------------------------------------------------------------------
            # if self.code == 'PA':
            #     total_paternity_leave_days = 0
            #     paternity_leave_ids = self.search([('employee_id','=',self.employee_id.id),('code','=','PA'),('state','in',['confirm','validate']),('financial_year_id','=',self.financial_year_id.id)])
            #     if paternity_leave_ids:
            #         existing_paternity_leave_days = 0
            #         for each_paternity_leave_id in paternity_leave_ids:
            #             existing_paternity_leave_days = existing_paternity_leave_days + each_paternity_leave_id.total_days
            #         total_paternity_leave_days = existing_paternity_leave_days +self.total_days
            #         if total_paternity_leave_days > self.holiday_status_id.maximum_allocation:
            #             raise UserError(_('Exceeding Limit! Maximum limit for %s is %s.') % (self.holiday_status_id.name,self.holiday_status_id.maximum_allocation))
            #     else:
            #         if self.total_days > self.holiday_status_id.maximum_allocation:
            #             raise UserError(_('Exceeding Limit! Maximum limit for %s is %s.') % (self.holiday_status_id.name,self.holiday_status_id.maximum_allocation))


            if self.code == 'PA':
                total_paternity_leave_days = 0
                paternity_leave_ids = self.search([('employee_id','=',self.employee_id.id),('code','=','PA'),('state','in',['confirm','validate']),('financial_year_id','=',self.financial_year_id.id)])
                if paternity_leave_ids:
                    existing_paternity_leave_days = 0
                    for each_paternity_leave_id in paternity_leave_ids:
                        existing_paternity_leave_days = existing_paternity_leave_days + each_paternity_leave_id.total_days
                    total_paternity_leave_days = existing_paternity_leave_days +self.total_days
                    if total_paternity_leave_days > self.holiday_status_id.maximum_allocation:
                        raise UserError(_('Exceeding Limit! Maximum limit for %s is %s.') % (self.holiday_status_id.name,self.holiday_status_id.maximum_allocation))
                else:
                    if self.total_days > self.holiday_status_id.maximum_allocation:
                        raise UserError(_('Exceeding Limit! Maximum limit for %s is %s.') % (self.holiday_status_id.name,self.holiday_status_id.maximum_allocation))


            #---------------------------------------------------------------------------------------------------------------------------            


            #Marriage leave logic-------------------------------------------------------------------------------------------------
            if self.code == 'MA':
                total_marriage_leave_days = 0
                marriage_leave_ids = self.search([('employee_id','=',self.employee_id.id),('code','=','MA'),('state','in',['confirm','validate']),('financial_year_id','=',self.financial_year_id.id)])
                if marriage_leave_ids:
                    existing_marriage_leave_days = 0
                    for each_marriage_leave_id in marriage_leave_ids:
                        existing_marriage_leave_days = existing_marriage_leave_days + each_marriage_leave_id.total_days
                    total_marriage_leave_days = existing_marriage_leave_days +self.total_days
                    if total_marriage_leave_days > self.holiday_status_id.maximum_allocation:
                        raise UserError(_('Exceeding Limit! Maximum limit for %s is %s.') % (self.holiday_status_id.name,self.holiday_status_id.maximum_allocation))
                else:
                    if self.total_days > self.holiday_status_id.maximum_allocation:
                        raise UserError(_('Exceeding Limit! Maximum limit for %s is %s.') % (self.holiday_status_id.name,self.holiday_status_id.maximum_allocation))
            #---------------------------------------------------------------------------------------------------------------------------            



            # Public holiday in leave duration--------------------------------------------------------------------------------------
            if self.code not in ('ML','MA', 'PA'):
                if not self.employee_id.site_master_id:
                    raise UserError(_('Site not assigned. Please get your site assigned from the HR before applying for leaves!'))
                if self.employee_id.site_master_id.holiday_ids:
                    public_holiday_dates = []
                    for each_holiday_id in self.employee_id.site_master_id.holiday_ids:
                        public_holiday_dates.append(each_holiday_id.holiday_date)
                    for each_date_item in date_list:
                        if each_date_item in public_holiday_dates:
                            raise UserError(_('The selected duration already has a public holiday !'))
            #---------------------------------------------------------------------------------------------------------------------
            



            # restrict the employee to apply holiday on weekoffs and sundays----------------------------------------------------------------------------------------------------
            # if 5 in holidays:
            #     # if self.code != 'OD':(commented as not required any further)
            #     if self.code != 'ML':
            #         if not self.employee_id.site_master_id:
            #             raise UserError(_('Site not assigned. Please get your site assigned from the HR before applying for leave on weekends!'))
            #         # all saturdays off
            #         if self.employee_id.site_master_id.weekoffs == 'all':
            #             raise UserError(_('The duration includes weekoff!'))
            #         # no saturdays off
            #         elif self.employee_id.site_master_id.weekoffs == 'no':
            #             pass
            #         # 2&4 or 1&3&5
            #         else:
            #             this_year = datetime.now().year
            #             for each_date in date_list:
            #                 each_date_str = datetime.strptime(each_date, "%Y-%m-%d")
            #                 if each_date_str.weekday() == 5:
            #                     duration_saturday = datetime.strptime(each_date, "%Y-%m-%d").day
            #                     duration_saturday_month = datetime.strptime(each_date, "%Y-%m-%d").month
            #             sat_holidays = {}
            #             for month in range(1, 13):
            #                 cal = calendar.monthcalendar(this_year, month)
            #                 if cal[0][calendar.SATURDAY]:
            #                     sat_holidays[month] = (
            #                         cal[1][calendar.SATURDAY],
            #                         cal[3][calendar.SATURDAY]
            #                     )
            #                 else:
            #                     sat_holidays[month] = (
            #                         cal[2][calendar.SATURDAY],
            #                         cal[4][calendar.SATURDAY]
            #                     )
            #             secondforth_saturdays = sat_holidays.get(duration_saturday_month)
            #             if self.employee_id.site_master_id.weekoffs == '2_4':                    
            #                 if duration_saturday in secondforth_saturdays:
            #                     raise UserError(_('The duration includes weekoff!'))
            #                 else:
            #                     pass
            #             else:
            #                 if duration_saturday not in secondforth_saturdays:
            #                     raise UserError(_('The duration includes weekoff!'))
            #                 else:
            #                     pass
            # if 6 in holidays:
            #     if self.code != 'ML':
            #         raise UserError(_('The duration includes Sunday!'))
            #-----------------------------------------------------------------------------------------------------------------------


            # restrict the employee to apply holiday on weekoffs and sundays except for sandwich----------------------------------------------------------------------------------------------------
            # continuous sandwich logic
            if 5 in holidays:
                # if self.code != 'OD':(commented as not required any further)
                if self.code not in ('ML','MA', 'PA'):
                    if not self.employee_id.site_master_id:
                        raise UserError(_('Site not assigned. Please get your site assigned from the HR before applying for leave on weekends!'))
                    # check if saturday is holiday or working
                    if self.employee_id.site_master_id.weekoffs == 'all':# means sat is off
                        # check for continuous FSSM
                        if 4 in holidays and 5 in holidays and 6 in holidays and 0 in holidays:
                            index_sat = holidays.index(5)
                            index_fri = index_sat-1
                            index_sun = index_sat+1
                            index_mon = index_sun+1
                            if holidays[index_fri] == 4 and holidays[index_sat] == 5 and holidays[index_sun] == 6 and holidays[index_mon] == 0:
                                fri_leave_id = None
                                mon_leave_id = None
                                for dt2 in rrule(DAILY, dtstart=dfn, until=dtn):
                                    # if leave taken is monday, find friday leave if any
                                    if dt2.weekday() == 0:
                                        fri = dt2-timedelta(days=3)
                                        deductable_ids = self.env['hr.holidays.status'].search([('deductable', '=', True)])
                                        fri_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', fri),('date_to_new', '=', fri)])
                                        if fri_leave_id:
                                            #if current is also deductable
                                            if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                                sat = dfn-timedelta(days=2)
                                                date_from_new_final = sat.strftime('%Y-%m-%d') # sat
                                                date_to_new_final = dtn.strftime('%Y-%m-%d') # dtn
                                                if not self.sandwich:
                                                    if not self.code in ('PA','MA'):
                                                        sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                                        return {
                                                            'name': _('Warning'),
                                                            'type': 'ir.actions.act_window',
                                                            'view_type': 'form',
                                                            'view_mode': 'form',
                                                            'res_model': 'sandwich.leaves',
                                                            'view_id': sandwich_leave_form.id,
                                                            'views': [(sandwich_leave_form.id, 'form')],
                                                            'target': 'new',
                                                            'context': {
                                                                'date_from_new':date_from_new_final,
                                                                'date_to_new':date_to_new_final,
                                                                'employee_id':self.employee_id.id}
                                                        }
                                    # if leave taken is friday, find monday leave if any
                                    if dt2.weekday() == 4:
                                        mon = dt2+timedelta(days=3)
                                        deductable_ids = self.env['hr.holidays.status'].search([('deductable', '=', True)])
                                        mon_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', mon),('date_to_new', '=', mon)])
                                        if mon_leave_id:
                                            #if current is also deductable
                                            if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                                sun = dtn+timedelta(days=2)
                                                date_from_new_final = dfn.strftime('%Y-%m-%d') #dfn
                                                date_to_new_final = sun.strftime('%Y-%m-%d') # sun
                                                if not self.sandwich:
                                                    if not self.code in ('PA','MA'):
                                                        sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                                        return {
                                                            'name': _('Warning'),
                                                            'type': 'ir.actions.act_window',
                                                            'view_type': 'form',
                                                            'view_mode': 'form',
                                                            'res_model': 'sandwich.leaves',
                                                            'view_id': sandwich_leave_form.id,
                                                            'views': [(sandwich_leave_form.id, 'form')],
                                                            'target': 'new',
                                                            'context': {
                                                                'date_from_new':date_from_new_final,
                                                                'date_to_new':date_to_new_final,
                                                                'employee_id':self.employee_id.id}
                                                        }
                            else:
                                raise UserError(_('The duration includes weekoff!'))
                        # no continuous FSSM
                        else:
                            raise UserError(_('The duration includes weekoff!'))
                    elif self.employee_id.site_master_id.weekoffs == 'no':# means all sat are working
                        # check for continuous SSM
                        if 5 in holidays and 6 in holidays and 0 in holidays:
                            index_sat = holidays.index(5)
                            index_sun = index_sat+1
                            index_mon = index_sun+1
                            if holidays[index_sat] == 5 and holidays[index_sun] == 6 and holidays[index_mon] == 0:
                                date_from_new_final = dfn.strftime('%Y-%m-%d')
                                date_to_new_final = dtn.strftime('%Y-%m-%d')
                                if not self.sandwich:
                                    if not self.code in ('PA','MA'):
                                        sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                        return {
                                            'name': _('Warning'),
                                            'type': 'ir.actions.act_window',
                                            'view_type': 'form',
                                            'view_mode': 'form',
                                            'res_model': 'sandwich.leaves',
                                            'view_id': sandwich_leave_form.id,
                                            'views': [(sandwich_leave_form.id, 'form')],
                                            'target': 'new',
                                            'context': {
                                                'date_from_new':date_from_new_final,
                                                'date_to_new':date_to_new_final,
                                                'employee_id':self.employee_id.id}
                                        }
                            else:
                                raise UserError(_('The duration includes weekoff!'))
                        # No continuous SSM
                        else:
                            pass

                    elif self.employee_id.site_master_id.weekoffs == 'saturday_weekoff': # all sat offs and all sun working
                        # check for continuous FSS
                        if 4 in holidays and 5 in holidays and 6 in holidays:
                            index_sat = holidays.index(5)
                            index_fri = index_sat-1
                            index_sun = index_sat+1
                            if holidays[index_fri] == 4 and holidays[index_sat] == 5 and holidays[index_sun] == 6:
                                date_from_new_final = dfn.strftime('%Y-%m-%d')
                                date_to_new_final = dtn.strftime('%Y-%m-%d')
                                if not self.sandwich:
                                    if not self.code in ('PA','MA'):
                                        sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                        return {
                                            'name': _('Warning'),
                                            'type': 'ir.actions.act_window',
                                            'view_type': 'form',
                                            'view_mode': 'form',
                                            'res_model': 'sandwich.leaves',
                                            'view_id': sandwich_leave_form.id,
                                            'views': [(sandwich_leave_form.id, 'form')],
                                            'target': 'new',
                                            'context': {
                                                'date_from_new':date_from_new_final,
                                                'date_to_new':date_to_new_final,
                                                'employee_id':self.employee_id.id}
                                        }
                            else:
                                raise UserError(_('The duration includes weekoff!'))
                        # no continuous FSSM
                        else:
                            raise UserError(_('The duration includes weekoff!')) 

                    else: # 2_4 or 1_3_5
                        this_year = datetime.now().year
                        for each_date in date_list:
                            each_date_str = datetime.strptime(each_date, "%Y-%m-%d")
                            if each_date_str.weekday() == 5:
                                duration_saturday = datetime.strptime(each_date, "%Y-%m-%d").day
                                duration_saturday_month = datetime.strptime(each_date, "%Y-%m-%d").month
                        sat_holidays = {}
                        for month in range(1, 13):
                            cal = calendar.monthcalendar(this_year, month)
                            if cal[0][calendar.SATURDAY]:
                                sat_holidays[month] = (
                                    cal[1][calendar.SATURDAY],
                                    cal[3][calendar.SATURDAY]
                                )
                            else:
                                sat_holidays[month] = (
                                    cal[2][calendar.SATURDAY],
                                    cal[4][calendar.SATURDAY]
                                )
                        secondforth_saturdays = sat_holidays.get(duration_saturday_month)
                        if self.employee_id.site_master_id.weekoffs == '2_4':   
                            if duration_saturday in secondforth_saturdays:
                                # this means the duration saturday is off
                                # check for continuous FSSM
                                if 4 in holidays and 5 in holidays and 6 in holidays and 0 in holidays:
                                    index_sat = holidays.index(5)
                                    index_fri = index_sat-1
                                    index_sun = index_sat+1
                                    index_mon = index_sun+1
                                    if holidays[index_fri] == 4 and holidays[index_sat] == 5 and holidays[index_sun] == 6 and holidays[index_mon] == 0:
                                        date_from_new_final = dfn.strftime('%Y-%m-%d')
                                        date_to_new_final = dtn.strftime('%Y-%m-%d')
                                        if not self.sandwich:
                                            if not self.code in ('PA','MA'):
                                                sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                                return {
                                                    'name': _('Warning'),
                                                    'type': 'ir.actions.act_window',
                                                    'view_type': 'form',
                                                    'view_mode': 'form',
                                                    'res_model': 'sandwich.leaves',
                                                    'view_id': sandwich_leave_form.id,
                                                    'views': [(sandwich_leave_form.id, 'form')],
                                                    'target': 'new',
                                                    'context': {
                                                        'date_from_new':date_from_new_final,
                                                        'date_to_new':date_to_new_final,
                                                        'employee_id':self.employee_id.id}
                                                }
                                    else:
                                        raise UserError(_('The duration includes weekoff!'))
                                # no continuous FSSM
                                else:
                                    raise UserError(_('The duration includes weekoff!'))
                            else:
                            # this means the duration saturday is working
                                # check for continuous SSM
                                if 5 in holidays and 6 in holidays and 0 in holidays:
                                    index_sat = holidays.index(5)
                                    index_sun = index_sat+1
                                    index_mon = index_sun+1
                                    if holidays[index_sat] == 5 and holidays[index_sun] == 6 and holidays[index_mon] == 0:
                                        date_from_new_final = dfn.strftime('%Y-%m-%d')
                                        date_to_new_final = dtn.strftime('%Y-%m-%d')
                                        if not self.sandwich:
                                            if not self.code in ('PA','MA'):
                                                sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                                return {
                                                    'name': _('Warning'),
                                                    'type': 'ir.actions.act_window',
                                                    'view_type': 'form',
                                                    'view_mode': 'form',
                                                    'res_model': 'sandwich.leaves',
                                                    'view_id': sandwich_leave_form.id,
                                                    'views': [(sandwich_leave_form.id, 'form')],
                                                    'target': 'new',
                                                    'context': {
                                                        'date_from_new':date_from_new_final,
                                                        'date_to_new':date_to_new_final,
                                                        'employee_id':self.employee_id.id}
                                                }
                                    else:
                                        raise UserError(_('The duration includes weekoff!'))
                                # No continuous SSM
                                else:
                                    pass
                        if self.employee_id.site_master_id.weekoffs == '1_3_5':   
                            if duration_saturday not in secondforth_saturdays:
                                # this means the duration saturday is off
                                # check for continuous FSSM
                                if 4 in holidays and 5 in holidays and 6 in holidays and 0 in holidays:
                                    index_sat = holidays.index(5)
                                    index_fri = index_sat-1
                                    index_sun = index_sat+1
                                    index_mon = index_sun+1
                                    if holidays[index_fri] == 4 and holidays[index_sat] == 5 and holidays[index_sun] == 6 and holidays[index_mon] == 0:
                                        date_from_new_final = dfn.strftime('%Y-%m-%d')
                                        date_to_new_final = dtn.strftime('%Y-%m-%d')
                                        if not self.sandwich:
                                            if not self.code in ('PA','MA'):
                                                sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                                return {
                                                    'name': _('Warning'),
                                                    'type': 'ir.actions.act_window',
                                                    'view_type': 'form',
                                                    'view_mode': 'form',
                                                    'res_model': 'sandwich.leaves',
                                                    'view_id': sandwich_leave_form.id,
                                                    'views': [(sandwich_leave_form.id, 'form')],
                                                    'target': 'new',
                                                    'context': {
                                                        'date_from_new':date_from_new_final,
                                                        'date_to_new':date_to_new_final,
                                                        'employee_id':self.employee_id.id}
                                                }
                                    else:
                                        raise UserError(_('The duration includes weekoff!'))
                                # no continuous FSSM
                                else:
                                    raise UserError(_('The duration includes weekoff!'))
                            else:
                                # this means the duration saturday is working
                                # check for continuous SSM
                                if 5 in holidays and 6 in holidays and 0 in holidays:
                                    index_sat = holidays.index(5)
                                    index_sun = index_sat+1
                                    index_mon = index_sun+1
                                    if holidays[index_sat] == 5 and holidays[index_sun] == 6 and holidays[index_mon] == 0:
                                        date_from_new_final = dfn.strftime('%Y-%m-%d')
                                        date_to_new_final = dtn.strftime('%Y-%m-%d')
                                        if not self.sandwich:
                                            if not self.code in ('PA','MA'):
                                                sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                                return {
                                                    'name': _('Warning'),
                                                    'type': 'ir.actions.act_window',
                                                    'view_type': 'form',
                                                    'view_mode': 'form',
                                                    'res_model': 'sandwich.leaves',
                                                    'view_id': sandwich_leave_form.id,
                                                    'views': [(sandwich_leave_form.id, 'form')],
                                                    'target': 'new',
                                                    'context': {
                                                        'date_from_new':date_from_new_final,
                                                        'date_to_new':date_to_new_final,
                                                        'employee_id':self.employee_id.id}
                                                }
                                    else:
                                        raise UserError(_('The duration includes weekoff!'))
                                # No continuous SSM
                                else:
                                    pass


            # if 6 in holidays:
            #     if self.code != 'ML':
            #         raise UserError(_('The duration includes Sunday!'))
            if 6 in holidays:
                if self.code not in ('ML','MA', 'PA'):
                    if not self.employee_id.site_master_id:
                        raise UserError(_('Site not assigned. Please get your site assigned from the HR before applying for leave on weekends!'))
                    # check if saturday is holiday or working
                    if self.employee_id.site_master_id.weekoffs == 'all':# means sat is off
                        # check for continuous FSSM
                        if 4 in holidays and 5 in holidays and 6 in holidays and 0 in holidays:
                            index_sat = holidays.index(5)
                            index_fri = index_sat-1
                            index_sun = index_sat+1
                            index_mon = index_sun+1
                            if holidays[index_fri] == 4 and holidays[index_sat] == 5 and holidays[index_sun] == 6 and holidays[index_mon] == 0:
                                date_from_new_final = dfn.strftime('%Y-%m-%d')
                                date_to_new_final = dtn.strftime('%Y-%m-%d')
                                if not self.sandwich:
                                    if not self.code in ('PA','MA'):
                                        sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                        return {
                                            'name': _('Warning'),
                                            'type': 'ir.actions.act_window',
                                            'view_type': 'form',
                                            'view_mode': 'form',
                                            'res_model': 'sandwich.leaves',
                                            'view_id': sandwich_leave_form.id,
                                            'views': [(sandwich_leave_form.id, 'form')],
                                            'target': 'new',
                                            'context': {
                                                'date_from_new':date_from_new_final,
                                                'date_to_new':date_to_new_final,
                                                'employee_id':self.employee_id.id}
                                        }
                            else:
                                raise UserError(_('The duration includes weekoff!'))
                        # no continuous FSSM
                        else:
                            raise UserError(_('The duration includes weekoff!'))
                    elif self.employee_id.site_master_id.weekoffs == 'no':# means sat is working
                        # check for continuous SSM
                        if 5 in holidays and 6 in holidays and 0 in holidays:
                            index_sat = holidays.index(5)
                            index_sun = index_sat+1
                            index_mon = index_sun+1
                            if holidays[index_sat] == 5 and holidays[index_sun] == 6 and holidays[index_mon] == 0:
                                date_from_new_final = dfn.strftime('%Y-%m-%d')
                                date_to_new_final = dtn.strftime('%Y-%m-%d')
                                if not self.sandwich:
                                    if not self.code in ('PA','MA'):
                                        sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                        return {
                                            'name': _('Warning'),
                                            'type': 'ir.actions.act_window',
                                            'view_type': 'form',
                                            'view_mode': 'form',
                                            'res_model': 'sandwich.leaves',
                                            'view_id': sandwich_leave_form.id,
                                            'views': [(sandwich_leave_form.id, 'form')],
                                            'target': 'new',
                                            'context': {
                                                'date_from_new':date_from_new_final,
                                                'date_to_new':date_to_new_final,
                                                'employee_id':self.employee_id.id}
                                        }
                            else:
                                raise UserError(_('The duration includes weekoff!'))
                        # No continuous SSM
                        else:
                            pass
                    elif self.employee_id.site_master_id.weekoffs == 'saturday_weekoff': # all sat off sun working
                        pass
                    else:# 2_4 or 1_3_5
                        if 5 in holidays:
                            this_year = datetime.now().year
                            for each_date in date_list:
                                each_date_str = datetime.strptime(each_date, "%Y-%m-%d")
                                if each_date_str.weekday() == 5:
                                    duration_saturday = datetime.strptime(each_date, "%Y-%m-%d").day
                                    duration_saturday_month = datetime.strptime(each_date, "%Y-%m-%d").month
                            sat_holidays = {}
                            for month in range(1, 13):
                                cal = calendar.monthcalendar(this_year, month)
                                if cal[0][calendar.SATURDAY]:
                                    sat_holidays[month] = (
                                        cal[1][calendar.SATURDAY],
                                        cal[3][calendar.SATURDAY]
                                    )
                                else:
                                    sat_holidays[month] = (
                                        cal[2][calendar.SATURDAY],
                                        cal[4][calendar.SATURDAY]
                                    )
                            secondforth_saturdays = sat_holidays.get(duration_saturday_month)
                            if self.employee_id.site_master_id.weekoffs == '2_4':   
                                if duration_saturday in secondforth_saturdays:
                                    # this means the duration saturday is off
                                    # check for continuous FSSM
                                    if 4 in holidays and 5 in holidays and 6 in holidays and 0 in holidays:
                                        index_sat = holidays.index(5)
                                        index_fri = index_sat-1
                                        index_sun = index_sat+1
                                        index_mon = index_sun+1
                                        if holidays[index_fri] == 4 and holidays[index_sat] == 5 and holidays[index_sun] == 6 and holidays[index_mon] == 0:
                                            date_from_new_final = dfn.strftime('%Y-%m-%d')
                                            date_to_new_final = dtn.strftime('%Y-%m-%d')
                                            if not self.sandwich:
                                                if not self.code in ('PA','MA'):
                                                    sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                                    return {
                                                        'name': _('Warning'),
                                                        'type': 'ir.actions.act_window',
                                                        'view_type': 'form',
                                                        'view_mode': 'form',
                                                        'res_model': 'sandwich.leaves',
                                                        'view_id': sandwich_leave_form.id,
                                                        'views': [(sandwich_leave_form.id, 'form')],
                                                        'target': 'new',
                                                        'context': {
                                                            'date_from_new':date_from_new_final,
                                                            'date_to_new':date_to_new_final,
                                                            'employee_id':self.employee_id.id}
                                                    }
                                        else:
                                            raise UserError(_('The duration includes weekoff!'))
                                    # no continuous FSSM
                                    else:
                                        raise UserError(_('The duration includes weekoff!'))
                                else:
                                # this means the duration saturday is working
                                    # check for continuous SSM
                                    if 5 in holidays and 6 in holidays and 0 in holidays:
                                        index_sat = holidays.index(5)
                                        index_sun = index_sat+1
                                        index_mon = index_sun+1
                                        if holidays[index_sat] == 5 and holidays[index_sun] == 6 and holidays[index_mon] == 0:
                                            date_from_new_final = dfn.strftime('%Y-%m-%d')
                                            date_to_new_final = dtn.strftime('%Y-%m-%d')
                                            if not self.sandwich:
                                                if not self.code in ('PA','MA'):
                                                    sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                                    return {
                                                        'name': _('Warning'),
                                                        'type': 'ir.actions.act_window',
                                                        'view_type': 'form',
                                                        'view_mode': 'form',
                                                        'res_model': 'sandwich.leaves',
                                                        'view_id': sandwich_leave_form.id,
                                                        'views': [(sandwich_leave_form.id, 'form')],
                                                        'target': 'new',
                                                        'context': {
                                                            'date_from_new':date_from_new_final,
                                                            'date_to_new':date_to_new_final,
                                                            'employee_id':self.employee_id.id}
                                                    }
                                        else:
                                            raise UserError(_('The duration includes weekoff!'))
                                    # No continuous SSM
                                    else:
                                        pass
                            if self.employee_id.site_master_id.weekoffs == '1_3_5':   
                                if duration_saturday not in secondforth_saturdays:
                                    # this means the duration saturday is off
                                    # check for continuous FSSM
                                    if 4 in holidays and 5 in holidays and 6 in holidays and 0 in holidays:
                                        index_sat = holidays.index(5)
                                        index_fri = index_sat-1
                                        index_sun = index_sat+1
                                        index_mon = index_sun+1
                                        if holidays[index_fri] == 4 and holidays[index_sat] == 5 and holidays[index_sun] == 6 and holidays[index_mon] == 0:
                                            date_from_new_final = dfn.strftime('%Y-%m-%d')
                                            date_to_new_final = dtn.strftime('%Y-%m-%d')
                                            if not self.sandwich:
                                                if not self.code in ('PA','MA'):
                                                    sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                                    return {
                                                        'name': _('Warning'),
                                                        'type': 'ir.actions.act_window',
                                                        'view_type': 'form',
                                                        'view_mode': 'form',
                                                        'res_model': 'sandwich.leaves',
                                                        'view_id': sandwich_leave_form.id,
                                                        'views': [(sandwich_leave_form.id, 'form')],
                                                        'target': 'new',
                                                        'context': {
                                                            'date_from_new':date_from_new_final,
                                                            'date_to_new':date_to_new_final,
                                                            'employee_id':self.employee_id.id}
                                                    }
                                        else:
                                            raise UserError(_('The duration includes weekoff!'))
                                    # no continuous FSSM
                                    else:
                                        raise UserError(_('The duration includes weekoff!'))
                                else:
                                    # this means the duration saturday is working
                                    # check for continuous SSM
                                    if 5 in holidays and 6 in holidays and 0 in holidays:
                                        index_sat = holidays.index(5)
                                        index_sun = index_sat+1
                                        index_mon = index_sun+1
                                        if holidays[index_sat] == 5 and holidays[index_sun] == 6 and holidays[index_mon] == 0:
                                            date_from_new_final = dfn.strftime('%Y-%m-%d')
                                            date_to_new_final = dtn.strftime('%Y-%m-%d')
                                            if not self.sandwich:
                                                if not self.code in ('PA','MA'):
                                                    sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                                    return {
                                                        'name': _('Warning'),
                                                        'type': 'ir.actions.act_window',
                                                        'view_type': 'form',
                                                        'view_mode': 'form',
                                                        'res_model': 'sandwich.leaves',
                                                        'view_id': sandwich_leave_form.id,
                                                        'views': [(sandwich_leave_form.id, 'form')],
                                                        'target': 'new',
                                                        'context': {
                                                            'date_from_new':date_from_new_final,
                                                            'date_to_new':date_to_new_final,
                                                            'employee_id':self.employee_id.id}
                                                    }
                                        else:
                                            raise UserError(_('The duration includes weekoff!'))
                                    # No continuous SSM
                                    else:
                                        pass
                        else:
                            raise UserError(_('The duration includes weekoff!'))

            #-----------------------------------------------------------------------------------------------------------------------

        


            # Broken S/W logic---------------------------------------------------------------------------------------------------------
            if self.sandwich:
                if self.holiday_status_id.sandwich == False:
                    raise UserError(_('You can apply only allocable leave types for sandwich policy or apply for leave without pay (PL,SL/CL,CO,LWP) !'))

            # all saturdays off
            if self.employee_id.site_master_id.weekoffs == 'all':
                date_from_new_final = None
                date_to_new_final = None
                fri_leave_id = None
                mon_leave_id = None
                for dt2 in rrule(DAILY, dtstart=dfn, until=dtn):
                    # if leave taken is monday, find friday leave if any
                    if dt2.weekday() == 0:
                        fri = dt2-timedelta(days=3)
                        deductable_ids = self.env['hr.holidays.status'].search([('deductable', '=', True)])
                        fri_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', fri),('date_to_new', '=', fri)])
                        if fri_leave_id:
                            #if current is also deductable
                            if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                sat = dfn-timedelta(days=2)
                                date_from_new_final = sat.strftime('%Y-%m-%d') # sat
                                date_to_new_final = dtn.strftime('%Y-%m-%d') # dtn
                                if not self.sandwich:
                                    if not self.code in ('PA','MA'):
                                        sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                        return {
                                            'name': _('Warning'),
                                            'type': 'ir.actions.act_window',
                                            'view_type': 'form',
                                            'view_mode': 'form',
                                            'res_model': 'sandwich.leaves',
                                            'view_id': sandwich_leave_form.id,
                                            'views': [(sandwich_leave_form.id, 'form')],
                                            'target': 'new',
                                            'context': {
                                                'date_from_new':date_from_new_final,
                                                'date_to_new':date_to_new_final,
                                                'employee_id':self.employee_id.id}
                                        }
                    # if leave taken is friday, find monday leave if any
                    if dt2.weekday() == 4:
                        mon = dt2+timedelta(days=3)
                        deductable_ids = self.env['hr.holidays.status'].search([('deductable', '=', True)])
                        mon_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', mon),('date_to_new', '=', mon)])
                        if mon_leave_id:
                            #if current is also deductable
                            if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                sun = dtn+timedelta(days=2)
                                date_from_new_final = dfn.strftime('%Y-%m-%d') #dfn
                                date_to_new_final = sun.strftime('%Y-%m-%d') # sun
                                if not self.sandwich:
                                    if not self.code in ('PA','MA'):
                                        sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                        return {
                                            'name': _('Warning'),
                                            'type': 'ir.actions.act_window',
                                            'view_type': 'form',
                                            'view_mode': 'form',
                                            'res_model': 'sandwich.leaves',
                                            'view_id': sandwich_leave_form.id,
                                            'views': [(sandwich_leave_form.id, 'form')],
                                            'target': 'new',
                                            'context': {
                                                'date_from_new':date_from_new_final,
                                                'date_to_new':date_to_new_final,
                                                'employee_id':self.employee_id.id}
                                        }

            # no saturday offs(all saturdays working)
            elif self.employee_id.site_master_id.weekoffs == 'no':
                sat_leave_id = None
                mon_leave_id = None
                for dt2 in rrule(DAILY, dtstart=dfn, until=dtn):
                    # if leave taken is monday, find saturday leave if any
                    if dt2.weekday() == 0:
                        sat = dt2-timedelta(days=2)
                        deductable_ids = self.env['hr.holidays.status'].search([('deductable', '=', True)])
                        sat_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', sat),('date_to_new', '=', sat)])
                        if sat_leave_id:
                            #if current is also deductable
                            if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                sun = dfn-timedelta(days=1)
                                date_from_new_final = sun.strftime('%Y-%m-%d') #sun
                                date_to_new_final = dtn.strftime('%Y-%m-%d') #dtn
                                if not self.sandwich:
                                    if not self.code in ('PA','MA'):
                                        sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                        return {
                                            'name': _('Warning'),
                                            'type': 'ir.actions.act_window',
                                            'view_type': 'form',
                                            'view_mode': 'form',
                                            'res_model': 'sandwich.leaves',
                                            'view_id': sandwich_leave_form.id,
                                            'views': [(sandwich_leave_form.id, 'form')],
                                            'target': 'new',
                                            'context': {
                                                'date_from_new':date_from_new_final,
                                                'date_to_new':date_to_new_final,
                                                'employee_id':self.employee_id.id
                                            }
                                        }  
                    # if leave taken is saturday, find monday leave if any
                    if dt2.weekday() == 5:
                        mon = dt2+timedelta(days=2)
                        deductable_ids = self.env['hr.holidays.status'].search([('deductable', '=', True)])
                        mon_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', mon),('date_to_new', '=', mon)])
                        if mon_leave_id:
                            #if current is also deductable
                            if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                sun = dtn+timedelta(days=1)
                                date_from_new_final = dfn.strftime('%Y-%m-%d') #dfn
                                date_to_new_final =  sun.strftime('%Y-%m-%d') #sun
                                if not self.sandwich:
                                    if not self.code in ('PA','MA'):
                                        sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                        return {
                                            'name': _('Warning'),
                                            'type': 'ir.actions.act_window',
                                            'view_type': 'form',
                                            'view_mode': 'form',
                                            'res_model': 'sandwich.leaves',
                                            'view_id': sandwich_leave_form.id,
                                            'views': [(sandwich_leave_form.id, 'form')],
                                            'target': 'new',
                                            'context': {
                                                'date_from_new':date_from_new_final,
                                                'date_to_new':date_to_new_final,
                                                'employee_id':self.employee_id.id
                                            }
                                        }


            # 2nd and 4th saturday off
            elif self.employee_id.site_master_id.weekoffs == '2_4':
                sat_leave_id = None
                mon_leave_id = None
                fri_leave_id = None
                deductable_ids = self.env['hr.holidays.status'].search([('deductable', '=', True)])
                for dt2 in rrule(DAILY, dtstart=dfn, until=dtn):
                    year_sf = datetime.now().year
                    month_sf = datetime.now().month
                    sat_holidays_sf = {}
                    for each_month in range(1, 13):
                        cal_sf = calendar.monthcalendar(year_sf, each_month)
                        if cal_sf[0][calendar.SATURDAY]:
                            sat_holidays_sf[each_month] = (
                                cal_sf[1][calendar.SATURDAY],
                                cal_sf[3][calendar.SATURDAY]
                            )
                        else:
                            sat_holidays_sf[each_month] = (
                                cal_sf[2][calendar.SATURDAY],
                                cal_sf[4][calendar.SATURDAY]
                            )
                    non_working_saturdays = sat_holidays_sf.get(month_sf)
                    # if monday is leave taken
                    if dt2.weekday() == 0:
                        # find out saturday
                        sat = dt2-timedelta(days=2)
                        sat_int = sat.day
                        fri = dt2-timedelta(days=3)
                        fri_int = fri.day
                        # check if saturday is a working. If yes, emp can apply leave on this day which leads us to sandwich leaves
                        if sat_int not in non_working_saturdays:
                            sat_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', sat),('date_to_new', '=', sat)])
                            if sat_leave_id:
                                #if current is also deductable
                                if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                    sun = dfn-timedelta(days=1)
                                    date_from_new_final = sun.strftime('%Y-%m-%d') #sun
                                    date_to_new_final = dtn.strftime('%Y-%m-%d') # dtn
                                    if not self.sandwich:
                                        if not self.code in ('PA','MA'):
                                            sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                            return {
                                                'name': _('Warning'),
                                                'type': 'ir.actions.act_window',
                                                'view_type': 'form',
                                                'view_mode': 'form',
                                                'res_model': 'sandwich.leaves',
                                                'view_id': sandwich_leave_form.id,
                                                'views': [(sandwich_leave_form.id, 'form')],
                                                'target': 'new',
                                                'context': {
                                                    'date_from_new':date_from_new_final,
                                                    'date_to_new':date_to_new_final,
                                                    'employee_id':self.employee_id.id
                                                }
                                            }   
                        # if saturday is holiday, it means emp cannot apply for leave on this day. So need to search for friday leave.
                        else:
                            fri_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', fri),('date_to_new', '=', fri)])
                            if fri_leave_id:
                                #if current is also deductable
                                if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                    sat = dfn-timedelta(days=2)
                                    date_from_new_final = sat.strftime('%Y-%m-%d') #sat
                                    date_to_new_final = dtn.strftime('%Y-%m-%d') #dtn
                                    if not self.sandwich:
                                        if not self.code in ('PA','MA'):
                                            sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                            return {
                                                'name': _('Warning'),
                                                'type': 'ir.actions.act_window',
                                                'view_type': 'form',
                                                'view_mode': 'form',
                                                'res_model': 'sandwich.leaves',
                                                'view_id': sandwich_leave_form.id,
                                                'views': [(sandwich_leave_form.id, 'form')],
                                                'target': 'new',
                                                'context': {
                                                    'date_from_new':date_from_new_final,
                                                    'date_to_new':date_to_new_final,
                                                    'employee_id':self.employee_id.id
                                                }
                                            }
                    # if saturday is leave taken
                    # saturday leave taken means saturday is working and need to only find monday leave because if at all saturday was holiday, system throws raise.
                    if dt2.weekday() == 5:
                        # find out monday
                        mon = dt2+timedelta(days=2)
                        mon_int = mon.day
                        # check if employee has any leave on monday
                        mon_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', mon),('date_to_new', '=', mon)])
                        if mon_leave_id:
                            #if current is also deductable
                            if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                sun = dtn+timedelta(days=1)
                                date_from_new_final = dfn.strftime('%Y-%m-%d') #dfn
                                date_to_new_final = sun.strftime('%Y-%m-%d') #sun
                                if not self.sandwich:
                                    if not self.code in ('PA','MA'):
                                        sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                        return {
                                            'name': _('Warning'),
                                            'type': 'ir.actions.act_window',
                                            'view_type': 'form',
                                            'view_mode': 'form',
                                            'res_model': 'sandwich.leaves',
                                            'view_id': sandwich_leave_form.id,
                                            'views': [(sandwich_leave_form.id, 'form')],
                                            'target': 'new',
                                            'context': {
                                                'date_from_new':date_from_new_final,
                                                'date_to_new':date_to_new_final,
                                                'employee_id':self.employee_id.id
                                            }
                                        }   
                    # if friday is leave taken
                    if dt2.weekday() == 4:
                        # find out saturday
                        sat = dt2+timedelta(days=1)
                        sat_int = sat.day
                        mon = dt2+timedelta(days=3)
                        # check if saturday is a holiday. If it is, find monday leave which can leave us to sandwich leaves.
                        # if saturday is working, finding monday leave logic is already implemented and so not needed ot be repeated here.
                        if sat_int in non_working_saturdays:
                            mon_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', mon),('date_to_new', '=', mon)])
                            if mon_leave_id:
                                #if current is also deductable
                                if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                    sun = dtn+timedelta(days=2)
                                    date_from_new_final = dfn.strftime('%Y-%m-%d') #dfn
                                    date_to_new_final = sun.strftime('%Y-%m-%d') #sun
                                    if not self.sandwich:
                                        if not self.code in ('PA','MA'):
                                            sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                            return {
                                                'name': _('Warning'),
                                                'type': 'ir.actions.act_window',
                                                'view_type': 'form',
                                                'view_mode': 'form',
                                                'res_model': 'sandwich.leaves',
                                                'view_id': sandwich_leave_form.id,
                                                'views': [(sandwich_leave_form.id, 'form')],
                                                'target': 'new',
                                                'context': {
                                                    'date_from_new':date_from_new_final,
                                                    'date_to_new':date_to_new_final,
                                                    'employee_id':self.employee_id.id
                                                }
                                            }
            

            # 1st, 3rd & 5th saturday off   
            elif self.employee_id.site_master_id.weekoffs == '1_3_5':
                sat_leave_id = None
                mon_leave_id = None
                fri_leave_id = None
                deductable_ids = self.env['hr.holidays.status'].search([('deductable', '=', True)])
                for dt2 in rrule(DAILY, dtstart=dfn, until=dtn):
                    year_ftf = dt2.year
                    month_ftf = dt2.month
                    sat_holidays_ftf = {}
                    for each_month in range(1, 13):
                        cal_ftf = calendar.monthcalendar(year_ftf, each_month)
                        if cal_ftf[0][calendar.SATURDAY]:
                            sat_holidays_ftf[each_month] = (
                                cal_ftf[1][calendar.SATURDAY],
                                cal_ftf[3][calendar.SATURDAY]
                            )
                        else:
                            sat_holidays_ftf[each_month] = (
                                cal_ftf[2][calendar.SATURDAY],
                                cal_ftf[4][calendar.SATURDAY]
                            )
                    working_saturdays = sat_holidays_ftf.get(month_ftf)
                    # if monday is leave taken
                    if dt2.weekday() == 0:
                        # find out saturday
                        sat = dt2-timedelta(days=2)
                        sat_int = sat.day
                        fri = dt2-timedelta(days=3)
                        fri_int = fri.day
                        # check if saturday is a working which means emp can apply leave on this day which leads us to sandwich leaves
                        if sat_int in working_saturdays:
                            sat_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', sat),('date_to_new', '=', sat)])
                            if sat_leave_id:
                                #if current is also deductable
                                if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                    sun = dfn-timedelta(days=1)
                                    date_from_new_final = sun.strftime('%Y-%m-%d') #sun
                                    date_to_new_final = dtn.strftime('%Y-%m-%d') #dtn
                                    if not self.sandwich:
                                        if not self.code in ('PA','MA'):
                                            sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                            return {
                                                'name': _('Warning'),
                                                'type': 'ir.actions.act_window',
                                                'view_type': 'form',
                                                'view_mode': 'form',
                                                'res_model': 'sandwich.leaves',
                                                'view_id': sandwich_leave_form.id,
                                                'views': [(sandwich_leave_form.id, 'form')],
                                                'target': 'new',
                                                'context': {
                                                    'date_from_new':date_from_new_final,
                                                    'date_to_new':date_to_new_final,
                                                    'employee_id':self.employee_id.id
                                                }
                                            }   
                        # saturday is a holiday which means emp cannot apply for leave on this day. So need to search for friday leave.
                        else:
                            fri_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', fri),('date_to_new', '=', fri)])
                            if fri_leave_id:
                                #if current is also deductable
                                if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                    sat = dfn-timedelta(days=2)
                                    date_from_new_final = sat.strftime('%Y-%m-%d') #sat
                                    date_to_new_final = dtn.strftime('%Y-%m-%d') #dtn
                                    if not self.sandwich:
                                        if not self.code in ('PA','MA'):
                                            sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                            return {
                                                'name': _('Warning'),
                                                'type': 'ir.actions.act_window',
                                                'view_type': 'form',
                                                'view_mode': 'form',
                                                'res_model': 'sandwich.leaves',
                                                'view_id': sandwich_leave_form.id,
                                                'views': [(sandwich_leave_form.id, 'form')],
                                                'target': 'new',
                                                'context': {
                                                    'date_from_new':date_from_new_final,
                                                    'date_to_new':date_to_new_final,
                                                    'employee_id':self.employee_id.id
                                                }
                                            }
                    # if saturday is leave taken
                    # saturday leave taken means saturday is working and need to only find monday leave because if at all saturday was holiday, system throws raise.
                    if dt2.weekday() == 5:
                        # find out monday
                        mon = dt2+timedelta(days=2)
                        mon_int = mon.day
                        # check if employee has any leave on monday
                        mon_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', mon),('date_to_new', '=', mon)])
                        if mon_leave_id:
                            #if current is also deductable
                            if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                sun = dtn+timedelta(days=1)
                                date_from_new_final = dfn.strftime('%Y-%m-%d') #dfn
                                date_to_new_final = sun.strftime('%Y-%m-%d') #sun
                                if not self.sandwich:
                                    if not self.code in ('PA','MA'):
                                        sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                        return {
                                            'name': _('Warning'),
                                            'type': 'ir.actions.act_window',
                                            'view_type': 'form',
                                            'view_mode': 'form',
                                            'res_model': 'sandwich.leaves',
                                            'view_id': sandwich_leave_form.id,
                                            'views': [(sandwich_leave_form.id, 'form')],
                                            'target': 'new',
                                            'context': {
                                                'date_from_new':date_from_new_final,
                                                'date_to_new':date_to_new_final,
                                                'employee_id':self.employee_id.id
                                            }
                                        }   
                    # if friday is leave taken
                    if dt2.weekday() == 4:
                        # find out saturday
                        sat = dt2+timedelta(days=1)
                        sat_int = sat.day
                        mon = dt2+timedelta(days=3)
                        # check if saturday is a holiday. If it is, find monday leave which can leave us to sandwich leaves.
                        # if saturday is working, finding monday leave logic is already implemented and so not needed ot be repeated here.
                        if sat_int not in working_saturdays:
                            mon_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', mon),('date_to_new', '=', mon)])
                            sun = dtn+timedelta(days=2)
                            date_from_new_final = dfn.strftime('%Y-%m-%d') #dfn
                            date_to_new_final = sun.strftime('%Y-%m-%d') #sun
                            if mon_leave_id:
                                #if current is also deductable
                                if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                    if not self.sandwich:
                                        if not self.code in ('PA','MA'):
                                            sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                            return {
                                                'name': _('Warning'),
                                                'type': 'ir.actions.act_window',
                                                'view_type': 'form',
                                                'view_mode': 'form',
                                                'res_model': 'sandwich.leaves',
                                                'view_id': sandwich_leave_form.id,
                                                'views': [(sandwich_leave_form.id, 'form')],
                                                'target': 'new',
                                                'context': {
                                                    'date_from_new':date_from_new_final,
                                                    'date_to_new':date_to_new_final,
                                                    'employee_id':self.employee_id.id
                                                }
                                            } 
            

            # only saturday offs  
            elif self.employee_id.site_master_id.weekoffs == 'saturday_weekoff': # all sat off all sun working
                sun_leave_id = None
                fri_leave_id = None
                deductable_ids = self.env['hr.holidays.status'].search([('deductable', '=', True)])
                for dt2 in rrule(DAILY, dtstart=dfn, until=dtn):
                    # if sunday is leave taken
                    if dt2.weekday() == 6:
                        # find out friday
                        fri = dt2-timedelta(days=2)
                        fri_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', fri),('date_to_new', '=', fri)])
                        if fri_leave_id:
                            #if current is also deductable
                            if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                sat = dt2-timedelta(days=1)
                                date_from_new_final = sat.strftime('%Y-%m-%d') #sat
                                date_to_new_final = dtn.strftime('%Y-%m-%d') #dtn
                                if not self.sandwich:
                                    if not self.code in ('PA','MA'):
                                        sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                        return {
                                            'name': _('Warning'),
                                            'type': 'ir.actions.act_window',
                                            'view_type': 'form',
                                            'view_mode': 'form',
                                            'res_model': 'sandwich.leaves',
                                            'view_id': sandwich_leave_form.id,
                                            'views': [(sandwich_leave_form.id, 'form')],
                                            'target': 'new',
                                            'context': {
                                                'date_from_new':date_from_new_final,
                                                'date_to_new':date_to_new_final,
                                                'employee_id':self.employee_id.id
                                            }
                                        }
                    # if friday is leave taken
                    if dt2.weekday() == 4:
                        # find out sunday
                        sun = dt2+timedelta(days=2)
                        sun_leave_id = self.search([('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('holiday_status_id', 'in', deductable_ids.ids),('half_day_presence', '=', False),'|',('date_from_new', '=', sun),('date_to_new', '=', sun)])
                        if sun_leave_id:
                            #if current is also deductable
                            if self.holiday_status_id.deductable == True and self.half_day_presence == False:
                                sat = dt2+timedelta(days=1)
                                date_from_new_final = dfn.strftime('%Y-%m-%d') #dfn
                                date_to_new_final = sat.strftime('%Y-%m-%d') #sat
                                if not self.sandwich:
                                    if not self.code in ('PA','MA'):
                                        sandwich_leave_form = self.env.ref('orient_leave_management.sandwich_leaves_form_view', False)
                                        return {
                                            'name': _('Warning'),
                                            'type': 'ir.actions.act_window',
                                            'view_type': 'form',
                                            'view_mode': 'form',
                                            'res_model': 'sandwich.leaves',
                                            'view_id': sandwich_leave_form.id,
                                            'views': [(sandwich_leave_form.id, 'form')],
                                            'target': 'new',
                                            'context': {
                                                'date_from_new':date_from_new_final,
                                                'date_to_new':date_to_new_final,
                                                'employee_id':self.employee_id.id
                                            }
                                        }
            #-----------------------------------------------------------------------------------------------------------------------
            

            # Work from home logic------------------------------------------------------------------------------------------------
            TWT = ['Tuesday','Wednesday','Thursday']
            date_from_month = datetime.strptime(self.date_from_new, "%Y-%m-%d").strftime('%B')
            date_from_day = datetime.strptime(self.date_from_new, "%Y-%m-%d").strftime('%A')
            date_from_year = datetime.strptime(self.date_from_new, "%Y-%m-%d").year
            if self.code == 'WFM':
                existing_wfm_ids = self.search([('employee_id','=',employee_id),('code','=','WFM'),('state','in',('confirm','validate'))])
                if existing_wfm_ids:
                    for each_existing_wfm_id in existing_wfm_ids:
                        existing_wfm_id_month = datetime.strptime(each_existing_wfm_id.date_from_new, "%Y-%m-%d").strftime('%B')
                        existing_wfm_id_year = datetime.strptime(each_existing_wfm_id.date_from_new, "%Y-%m-%d").year
                        if existing_wfm_id_month == date_from_month and existing_wfm_id_year == date_from_year:
                            raise UserError(_('Sorry. You have already availed one WFM for %s!') % (date_from_month))
                if no_of_days > 1:
                    raise UserError(_('Sorry. Only a single WFM can be availed per month!'))
                if date_from_day not in TWT:
                    raise UserError(_('Sorry. WFM can be availed only on the following days: (Tuesday, Wednesday, Thursday)! '))
                for dt3 in rrule(DAILY, dtstart=dfn, until=dfn):
                    previous_day = dt3-timedelta(days=1)
                    next_day = dt3+timedelta(days=1)
                previous_day_holiday = holiday_obj.search([('holiday_date','=',previous_day)])
                next_day_holiday = holiday_obj.search([('holiday_date','=',next_day)])
                if previous_day_holiday and  previous_day_holiday in self.employee_id.holiday_ids:
                    raise UserError(_('Sorry. WFM cannot be clubbed with public holidays !'))
                if next_day_holiday and  next_day_holiday in self.employee_id.holiday_ids:
                    raise UserError(_('Sorry. WFM cannot be clubbed with public holidays !'))
            #---------------------------------------------------------------------------------------------------------------------


            #comp-off logic----------------------------------------------------------------------------------------------------------
            if code =='CO':
                if self.total_days > 1:
                    raise UserError(_('You can only apply one Compensatory leave at a time. Please make sure the duration is 1 day !'))
                comp_off_dates = []
                applied_co_ids = self.env['hr.holidays'].search([('code', '=', 'CO'),('employee_id', '=', self.employee_id.id),('comp_off_date', '=', self.comp_off_date),('state', 'in', ['confirm','validate']),('id', '!=', self.id)])
                if applied_co_ids:
                    raise UserError(_('You have already applied for Compensatory off on %s!') % (self.comp_off_date))
                allocated_co_ids = self.env['hr.holidays'].search([('code', '=', 'CO'),('employee_id', '=', self.employee_id.id),('allocated', '=', True)])
                for allocated_co_id in allocated_co_ids:
                    comp_off_dates.append(allocated_co_id.comp_off_date)
                if comp_off_dates:
                    if self.comp_off_date not in comp_off_dates:
                        raise UserError(_('Available Compensatory dates for you are : %s !') % (comp_off_dates))
                comp_off_date = datetime.strptime(self.comp_off_date, '%Y-%m-%d')
                difference =  abs((dfn - comp_off_date).days)
                if difference > 30:
                    raise UserError(_('Sorry you cannot apply for this leave ! This Comp Off is either already lapsed or will lapse for the selected duration!'))
                pre1 = dfn-timedelta(days=1)
                pre2 = dfn-timedelta(days=2)
                pre1_id = self.search([('code', '=', 'CO'),('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('date_from_new', '=', pre1)])
                pre2_id = self.search([('code', '=', 'CO'),('employee_id', '=', self.employee_id.id),('state', 'in', ['confirm','validate']),('date_from_new', '=', pre2)])
                if pre1_id and pre2_id:
                    raise UserError(_('You cannot apply for 3 consecutive compensatory leaves!'))
                # the holiday being taken should surpass the comp-off date and -----------------------------------------------------------
                # the holiday being taken and comp-off day cannot be the same day---------------------------------------------------------
                if dfn < comp_off_date or dfn == comp_off_date:
                    raise UserError(_('Invalid Comp Off Date!'))
                #-------------------------------------------------------------------------------------------------------------------------
            

            #attendance object creation-----------------------------------------------------------------------------------------------
            # if no_of_days == 1.0:
            #     leave_date = str(dfn)[:10]
            #     attendance_id = attendance_obj.search([('employee_id','=',employee_id), ('attendance_date','=',leave_date),('employee_status','=','AB')])
            #     if attendance_id:
            #         if attendance_id.in_time == False or attendance_id.in_time == '':
            #             pass
            #         else:
            #             raise UserError(_('Sorry. Cannot apply for a leave since you were present on that day'))
            #     else:
            #         leave_date1 = datetime.strptime(leave_date, '%Y-%m-%d').date()
            #         leave_datetime = datetime.strptime(leave_date1.strftime('%Y%m%d'), '%Y%m%d')
            #         attendance_obj.create({'employee_id':employee_id,
            #                                'check_in':leave_datetime,
            #                                'check_out':leave_datetime,
            #                                'employee_code':self.employee_id.emp_code,
            #                                'department_id_val':self.employee_id.department_id.id,
            #                                'attendance_date':leave_date1})
            # elif no_of_days > 1.0:
            #     for dd in date_list:
            #         leave_date = datetime.strptime(dd, '%Y-%m-%d').date()
            #         attendance_id = attendance_obj.search([('employee_id','=',employee_id), ('attendance_date','=',leave_date),('employee_status','=','AB')])
            #         if attendance_id:
            #             if attendance_id.in_time == False or attendance_id.in_time == '':
            #                 attendance_id.write({'employee_status':code,'state':'done'})
            #         else:
            #             leave_datetime = datetime.strptime(leave_date.strftime('%Y%m%d'), '%Y%m%d')
            #             attendance_obj.create({'employee_id':employee_id,
            #                                    'check_in':leave_datetime,'check_out':leave_datetime,
            #                                    'employee_code':self.employee_id.emp_code,
            #                                    'department_id_val':self.employee_id.department_id.id,
            #                                    'attendance_date':leave_date})
            #------------------------------------------------------------------------------------------------------------------------
        

        # updating balanced-days logic------------------------------------------------------------------------------------------------
        if self.filtered(lambda holiday: holiday.state != 'draft'):
            raise UserError(_('Leave request must be in "Draft" state in order to apply it.'))
        if self.code == 'CO':
            allocated_leave_id = self.search([('employee_id', '=', self.employee_id.id),('type', '=', 'add'),('code', '=', self.code),('comp_off_date', '=', self.comp_off_date)])
        else:
            allocated_leave_id = self.search([('employee_id', '=', self.employee_id.id),('type', '=', 'add'),('code', '=', self.code)])
        if allocated_leave_id:
            balanced_days = allocated_leave_id.balanced_days-self.total_days
            self.env.cr.execute("update hr_holidays set balanced_days=%s where id=%s" %(balanced_days,str(allocated_leave_id.id)))
        vals = {'state':'confirm'}
        #----------------------------------------------------------------------------------------------------------------------------       
        

        # half-day logic-------------------------------------------------------------------------------------------------------------
        if self.half_day_applicable:
            if self.date_from_new != self.date_to_new:
                raise UserError(_('Half can be applicable only for a single day. Select dates properly !'))
            worked_hours = 0.0
            attendance_id = self.env['hr.attendance'].search([('employee_id','=',self.employee_id.id),('attendance_date','=',self.date_from_new)],limit=1)
            if attendance_id.worked_hours:
                worked_hours = attendance_id.worked_hours
            if worked_hours >= 4.30 and worked_hours < 8.0:
                pass
            else:
                raise UserError(_('You cannot apply for half day leave as it is applicable only if your working hours for the selected date fall between 4.5 hours to 8 hours ! Check attendances for more details.'))
            vals.update({'total_days':0.5,'half_day_applicable':'t'})
        #-----------------------------------------------------------------------------------------------------------------------------
        
        # half-day OD logic-----------------------------------------------------------------------------------------------------------
        if self.half_od_applicable:
            if self.date_from_new != self.date_to_new:
                raise UserError(_('Half OD can be applicable only for a single day. Select dates properly !'))
        #-----------------------------------------------------------------------------------------------------------------------------

        template_id = self.env.ref('orient_leave_management.email_template_for_leavesapproval', False)
        self.env['mail.template'].browse(template_id.id).send_mail(self.id, force_send=True)
        if self.request_type == 'od' and self.holiday_status_od_id:
            vals.update({'holiday_status_id':self.holiday_status_od_id.id,'code':'OD'})
        return self.write(vals)


    @api.multi
    def action_approve(self):
        # if double_validation: this method is the first approval approval
        # if not double_validation: this method calls action_validate() below
        self._check_security_action_approve()
        current_employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        for holiday in self:
            self.approved_by = current_employee.id
            if holiday.state != 'confirm':
                raise UserError(_('Leave request must be submitted in order to approve it.'))
            if holiday.double_validation:
                return holiday.write({'state': 'validate1', 'first_approver_id': current_employee.id})
            else:
                holiday.action_validate()


    @api.multi
    def action_validate(self):
        self._check_security_action_validate()
        current_employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        for holiday in self:
            attendance_obj = self.env['hr.attendance']
            shift_obj = self.env['hr.employee.shift.timing']
            employee_id = self.employee_id.id
            code = self.code
            no_of_days = self.total_days
            dfn = datetime.strptime(self.date_from_new, '%Y-%m-%d')
            dtn = datetime.strptime(self.date_to_new, '%Y-%m-%d')
            date_list = []
            # datelist(leaves from,leaves to)-----------------------------------------------------------------------------
            for dt in rrule(DAILY, dtstart=dfn, until=dtn):
                date_list.append(datetime.strftime(dt,"%Y-%m-%d"))
            #-------------------------------------------------------------------------------------------------------------
            # Raises------------------------------------------------------------------------------------------------------
            if holiday.state not in ['confirm', 'validate1']:
                raise UserError(_('Leave request must be submitted in order to approve it.'))
            if holiday.state == 'validate1' and not holiday.env.user.has_group('hr_holidays.group_hr_holidays_manager'):
                raise UserError(_('Only an HR Manager can apply the second approval on leave requests.'))
            #---------------------------------------------------------------------------------------------------------------
            # Attendance update---------------------------------------------------------------------------------------------
            g18_shift_id = shift_obj.search([('name','=','G18')])
            if no_of_days == 1.0:
                leave_date = str(dfn)[:10]
                attendance_records = attendance_obj.search([('employee_id','=',employee_id),('attendance_date','=',leave_date)])
                if code == 'OD':
                    early_leaving = ''
                    late_coming = ''
                    worked_hours = attendance_records.worked_hours
                    if attendance_records:
                        if attendance_records.employee_status == 'AB':
                            employee_status = 'OD'
                        elif attendance_records.employee_status == '' or attendance_records.employee_status == ' ':
                            employee_status = 'OD'
                        else:
                            raise UserError(_('Not applicable!'))
                        if attendance_records.employee_id.shift_id == g18_shift_id:
                            worked_hours = 7.00
                        else:
                            worked_hours = 9.00
                    else:
                        employee_status = 'OD'
                        if self.employee_id.shift_id == g18_shift_id:
                            worked_hours = 7.00
                        else:
                            worked_hours = 9.00
                else:
                    worked_hours = attendance_records.worked_hours
                    early_leaving = attendance_records.early_leaving if attendance_records.early_leaving else ''
                    late_coming = attendance_records.late_coming if attendance_records.early_leaving else ''
                    employee_status = code
                if attendance_records:
                    for attendance_record in attendance_records:
                        self.env.cr.execute("update hr_attendance set employee_status='%s',state='done',worked_hours=%s,early_leaving='%s',late_coming='%s' where id=%s" %(str(employee_status),worked_hours,str(early_leaving),str(late_coming),attendance_record.id))
                else:    
                    leave_date1 = datetime.strptime(leave_date, '%Y-%m-%d').date()
                    leave_datetime = datetime.strptime(leave_date1.strftime('%Y%m%d'), '%Y%m%d')
                    attendance_obj.create(
                        {
                            'employee_id':employee_id,
                            'check_in':leave_datetime,
                            'check_out':leave_datetime,
                            'employee_code':self.employee_id.emp_code,
                            'department_id_val':self.employee_id.department_id.id,
                            'site_master_id':self.employee_id.site_master_id.id,
                            'shift':self.employee_id.shift_id.id,
                            'attendance_date':leave_date1,
                            'employee_status':code,
                            'state':'done',
                            'worked_hours': worked_hours,
                            'early_leaving': early_leaving,
                            'late_coming': late_coming
                        })
            elif no_of_days > 1.0:
                for dd in date_list:
                    leave_date = datetime.strptime(dd, '%Y-%m-%d').date()
                    attendance_records = attendance_obj.search([('employee_id','=',employee_id),('attendance_date','=',leave_date)])
                    if attendance_records:
                        for attendance_record in attendance_records:
                            self.env.cr.execute("update hr_attendance set employee_status='%s',state='done' where id=%s" %(str(code),attendance_record.id))
                    else:
                        leave_datetime = datetime.strptime(leave_date.strftime('%Y%m%d'), '%Y%m%d')
                        attendance_obj.create(
                            {
                                'employee_id':employee_id,
                                'check_in':leave_datetime,
                                'check_out':leave_datetime,
                                'employee_code':self.employee_id.emp_code,
                                'department_id_val':self.employee_id.department_id.id,
                                'site_master_id':self.employee_id.site_master_id.id,
                                'shift':self.employee_id.shift_id.id,
                                'attendance_date':leave_date,
                                'employee_status':code,
                                'state':'done'
                            })
            elif no_of_days == 0.5:
                leave_date = str(dfn)[:10]
                attendance_id = attendance_obj.search([('employee_id','=',employee_id), ('attendance_date','=',leave_date)])    
                early_leaving = ''
                late_coming = ''
                if code == 'PL':
                    employee_status = 'half_day_pl'
                elif code == 'SL/CL':
                    employee_status = 'half_day_sl'
                elif code == 'CL':
                    employee_status = 'half_day_cl'
                elif code == 'OD':
                    if attendance_id:
                        if attendance_id.employee_status == 'AB':
                            employee_status = 'half_ab_half_od'
                        elif attendance_id.employee_status == 'half_day_p_ab':
                            employee_status = 'half_p_half_od'
                        elif attendance_id.employee_status == '' or attendance_id.employee_status == ' ':
                            employee_status = 'half_ab_half_od'
                        else:
                            raise UserError(_('Not applicable!'))
                    else:
                        employee_status = 'half_ab_half_od'
                if attendance_id:
                    self.env.cr.execute("update hr_attendance set employee_status='%s',state='done',early_leaving='%s',late_coming='%s' where id=%s" %(str(employee_status),str(early_leaving),str(late_coming),attendance_id.id))
                else:
                    leave_date1 = datetime.strptime(leave_date, '%Y-%m-%d').date()
                    leave_datetime = datetime.strptime(leave_date1.strftime('%Y%m%d'), '%Y%m%d')
                    attendance_obj.create(
                        {
                            'employee_id':employee_id,
                            'check_in':leave_datetime,
                            'check_out':leave_datetime,
                            'employee_code':self.employee_id.emp_code,
                            'department_id_val':self.employee_id.department_id.id,
                            'site_master_id':self.employee_id.site_master_id.id,
                            'shift':self.employee_id.shift_id.id,
                            'attendance_date':leave_date1,
                            'employee_status':employee_status,
                            'state':'done', 
                            'early_leaving':early_leaving,
                            'late_coming':late_coming
                        })
            #-------------------------------------------------------------------------------------------------------------
            holiday.write({'state': 'validate'})
            if holiday.double_validation:
                holiday.write({'second_approver_id': current_employee.id})
            else:
                holiday.write({'first_approver_id': current_employee.id})
            if holiday.holiday_type == 'employee' and holiday.type == 'remove':
                holiday._validate_leave_request()
            elif holiday.holiday_type == 'category':
                leaves = self.env['hr.holidays']
                for employee in holiday.category_id.employee_ids:
                    values = holiday._prepare_create_by_category(employee)
                    leaves += self.with_context(mail_notify_force_send=False).create(values)
                # TODO is it necessary to interleave the calls?
                leaves.action_approve()
                if leaves and leaves[0].double_validation:
                    leaves.action_validate()
        template_id = self.env.ref('orient_leave_management.email_template_for_leavesapproved', False)
        self.env['mail.template'].browse(template_id.id).send_mail(self.id, force_send=True)
        return True


    @api.multi
    def action_refuse(self):
        self._check_security_action_refuse()
        current_employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)

        if not self.report_note:
            raise UserError(_('Kindly add a reason for rejection in comments!'))

        for holiday in self:
            if holiday.state not in ['confirm', 'validate', 'validate1']:
                raise UserError(_('Leave request must be submitted or approved in order to reject it.'))

            if holiday.state == 'validate1':
                holiday.write({'state': 'refuse','refused_by':current_employee.id, 'first_approver_id': current_employee.id})
            else:   
                holiday.write({'state': 'refuse','refused_by':current_employee.id, 'second_approver_id': current_employee.id})
            # Delete the meeting
            if holiday.meeting_id:
                holiday.meeting_id.unlink()
            # If a category that created several holidays, cancel all related
            # holiday.linked_request_ids.action_refuse()
        self._remove_resource_leave()
        if self.code == 'CO':
            allocated_leave_id = self.search([('employee_id', '=', self.employee_id.id),('type', '=', 'add'),('code', '=', self.code),('comp_off_date', '=', self.comp_off_date)])
        else:
            allocated_leave_id = self.search([('employee_id', '=', self.employee_id.id),('type', '=', 'add'),('code', '=', self.code)])
        if allocated_leave_id:
            balanced_days = allocated_leave_id.balanced_days+self.total_days
            allocated_leave_id.write({'balanced_days':balanced_days})
        template_id = self.env.ref('orient_leave_management.email_template_for_leavesrefused', False)
        self.env['mail.template'].browse(template_id.id).send_mail(self.id, force_send=True)
        return True


    @api.multi
    def action_allocate(self):
        # check if the selected leave type is allocable------------------------------------------------------------------------------
        if self.holiday_status_id.allocable == False:
            raise UserError(_("%s are not allocable") % (self.holiday_status_id.name))
        #----------------------------------------------------------------------------------------------------------------------------

        # check if the employee is confirmed before allocating-----------------------------------------------------------------------
        if self.holiday_status_id.applicable_to == 'confirmed':
            if self.employee_id.position_type == 'probation':
                raise UserError(_("%s are allocable only for confirmed employees.") % (self.holiday_status_id.name))
        #----------------------------------------------------------------------------------------------------------------------------

        # check if comp-off is already allocated for the selected comp-off date------------------------------------------------------
        existing_co_date_id = self.env['hr.holidays'].search([('comp_off_date', '=', self.comp_off_date),('allocated', '=', True),('id', '!=', self.id)])
        if self.holiday_status_id.code == 'CO' and existing_co_date_id and existing_co_date_id!=self.id:
            raise UserError(_("Compensatory off is already allocated against %s !") % (self.comp_off_date))
        #----------------------------------------------------------------------------------------------------------------------------
       
       # check if comp-off being allocated is for future date------------------------------------------------------------------------
        if dfn < comp_off_date or dfn == comp_off_date or comp_off_date > datetime.now():
            raise UserError(_('Invalid Comp Off Date!'))
        #----------------------------------------------------------------------------------------------------------------------------

        #double-validation logic-----------------------------------------------------------------------------------------------------
        self._check_security_action_validate()
        current_employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        for holiday in self:
            if holiday.double_validation:
                holiday.write({'second_approver_id': current_employee.id})
            else:
                holiday.write({'first_approver_id': current_employee.id})
            if holiday.holiday_type == 'employee' and holiday.type == 'remove':
                holiday._validate_leave_request()
            elif holiday.holiday_type == 'category':
                leaves = self.env['hr.holidays']
                for employee in holiday.category_id.employee_ids:
                    values = holiday._prepare_create_by_category(employee)
                    leaves += self.with_context(mail_notify_force_send=False).create(values)
                # TODO is it necessary to interleave the calls?
                leaves.action_approve()
                if leaves and leaves[0].double_validation:
                    leaves.action_validate()
        #-----------------------------------------------------------------------------------------------------------------------------

        #updating balanced leaves and other values------------------------------------------------------------------------------------
        vals = {'state': 'allocated','allocated':True,'balanced_days':self.total_days}
        if self.holiday_status_id.code == 'CO':
            vals.update({'total_days':1})
        #-----------------------------------------------------------------------------------------------------------------------------
        return self.write(vals)

    @api.multi
    def _create_resource_leave(self):
        """ This method will create entry in resource calendar leave object at the time of holidays validated """
        for leave in self:
            self.env['resource.calendar.leaves'].create({
                'name': leave.name,
                'date_from': leave.date_from_new,
                'holiday_id': leave.id,
                'date_to': leave.date_to_new,
                'resource_id': leave.employee_id.resource_id.id,
                'calendar_id': leave.employee_id.resource_calendar_id.id
            })
        return True

    @api.multi
    def _prepare_create_by_category(self, employee):
        self.ensure_one()
        values = {
            'name': self.name,
            'type': self.type,
            'holiday_type': 'employee',
            'holiday_status_id': self.holiday_status_id.id,
            'date_from_new': self.date_from_new,
            'date_to_new': self.date_to_new,
            'notes': self.notes,
            'total_days': self.total_days,
            'parent_id': self.id,
            'employee_id': employee.id
        }
        return values


    def _prepare_holidays_meeting_values(self):
        self.ensure_one()
        meeting_values = {
            'name': self.display_name,
            'categ_ids': [(6, 0, [
                self.holiday_status_id.categ_id.id])] if self.holiday_status_id.categ_id else [],
            'duration': self.total_days * HOURS_PER_DAY,
            'description': self.notes,
            'user_id': self.user_id.id,
            'start': self.date_from_new,
            'stop': self.date_to_new,
            'allday': False,
            'state': 'open',  # to block that meeting date in the calendar
            'privacy': 'confidential'
        }
        # Add the partner_id (if exist) as an attendee
        if self.user_id and self.user_id.partner_id:
            meeting_values['partner_ids'] = [
                (4, self.user_id.partner_id.id)]
        return meeting_values



class Employee(models.Model):
    _inherit = "hr.employee"

    site_master_id = fields.Many2one('site.master','Site',track_visibility='onchange')
    holiday_ids = fields.Many2many('holiday.master', 'employee_holiday_rel', 'employee_id', 'holiday_id', string='Holidays')
    # site_ids = fields.Many2many('site.master', 'employee_site_rel', 'site_id', 'employee_id', string='Sites')



    @api.onchange('site_master_id')
    def onchange_site_master_id(self):
        domain = {}
        data = {}
        if self.site_master_id:
            data['holiday_ids'] = [(6,0,self.site_master_id.holiday_ids.ids)]
        else:
            data['holiday_ids'] = []
        return {'domain':domain,'value':data}
        

    @api.onchange('holiday_status_id')
    def onchange_code(self):
        data = {}
        holiday_stat_id = self.env['hr.holidays.status'].search([('code','=','CO')])
        if self.holiday_status_id.name==holiday_stat_id.name:
            data['comp_off'] = True
        else:
            data['comp_off'] = False
        if self.holiday_status_id:
            data['code'] = self.holiday_status_id.code
        else:
            data['code'] = None
        if self.holiday_status_id == holiday_stat_id and self.type=='add':
            data['total_days'] = 1
        return {'value':data}

    def _get_remaining_leaves(self):
        """ Helper to compute the remaining leaves for the current employees
            :returns dict where the key is the employee id, and the value is the remain leaves
        """
        self._cr.execute("""
            SELECT
                sum(h.total_days) AS days,
                h.employee_id
            FROM
                hr_holidays h
                join hr_holidays_status s ON (s.id=h.holiday_status_id)
            WHERE
                h.state='validate' AND
                s.limit=False AND
                h.employee_id in %s
            GROUP BY h.employee_id""", (tuple(self.ids),))
        return dict((row['employee_id'], row['days']) for row in self._cr.dictfetchall())

    @api.multi
    def _inverse_remaining_leaves(self):
        status_list = self.env['hr.holidays.status'].search([('limit', '=', False)])
        # Create leaves (adding remaining leaves) or raise (reducing remaining leaves)
        actual_remaining = self._get_remaining_leaves()
        for employee in self.filtered(lambda employee: employee.remaining_leaves):
            # check the status list. This is done here and not before the loop to avoid raising
            # exception on employee creation (since we are in a computed field).
            if len(status_list) != 1:
                raise UserError(_("The feature behind the field 'Remaining Legal Leaves' can only be used when there is only one "
                    "leave type with the option 'Allow to Override Limit' unchecked. (%s Found). "
                    "Otherwise, the update is ambiguous as we cannot decide on which leave type the update has to be done. "
                    "\n You may prefer to use the classic menus 'Leave Requests' and 'Allocation Requests' located in Leaves Application "
                    "to manage the leave days of the employees if the configuration does not allow to use this field.") % (len(status_list)))
            status = status_list[0] if status_list else None
            if not status:
                continue
            # if a status is found, then compute remaing leave for current employee
            difference = employee.remaining_leaves - actual_remaining.get(employee.id, 0)
            if difference > 0:
                leave = self.env['hr.holidays'].create({
                    'name': _('Allocation for %s') % employee.name,
                    'employee_id': employee.id,
                    'holiday_status_id': status.id,
                    'type': 'add',
                    'holiday_type': 'employee',
                    'total_days': difference
                })
                leave.action_approve()
                if leave.double_validation:
                    leave.action_validate()
            elif difference < 0:
                raise UserError(_('You cannot reduce validated allocation requests'))

    @api.multi
    def _compute_leaves_count(self):
        leaves = self.env['hr.holidays'].read_group([
            ('employee_id', 'in', self.ids),
            ('holiday_status_id.limit', '=', False),
            ('state', '=', 'validate')
        ], fields=['total_days', 'employee_id'], groupby=['employee_id'])
        mapping = dict([(leave['employee_id'][0], leave['total_days']) for leave in leaves])
        for employee in self:
            employee.leaves_count = mapping.get(employee.id)

    @api.multi
    def _compute_leave_status(self):
        # Used SUPERUSER_ID to forcefully get status of other user's leave, to bypass record rule
        holidays = self.env['hr.holidays'].sudo().search([
            ('employee_id', 'in', self.ids),
            ('date_from_new', '<=', fields.Datetime.now()),
            ('date_to_new', '>=', fields.Datetime.now()),
            ('type', '=', 'remove'),
            ('state', 'not in', ('cancel', 'refuse'))
        ])
        leave_data = {}
        for holiday in holidays:
            leave_data[holiday.employee_id.id] = {}
            leave_data[holiday.employee_id.id]['leave_date_from'] = holiday.date_from_new
            leave_data[holiday.employee_id.id]['leave_date_to'] = holiday.date_to_new
            leave_data[holiday.employee_id.id]['current_leave_state'] = holiday.state
            leave_data[holiday.employee_id.id]['current_leave_id'] = holiday.holiday_status_id.id

        for employee in self:
            employee.leave_date_from = leave_data.get(employee.id, {}).get('leave_date_from')
            employee.leave_date_to = leave_data.get(employee.id, {}).get('leave_date_to')
            employee.current_leave_state = leave_data.get(employee.id, {}).get('current_leave_state')
            employee.current_leave_id = leave_data.get(employee.id, {}).get('current_leave_id')


    @api.multi
    def _compute_absent_employee(self):
        today_date = datetime.datetime.utcnow().date()
        today_start = fields.Datetime.to_string(today_date)  # get the midnight of the current utc day
        today_end = fields.Datetime.to_string(today_date + relativedelta(hours=23, minutes=59, seconds=59))
        data = self.env['hr.holidays'].read_group([
            ('employee_id', 'in', self.ids),
            ('state', 'not in', ['cancel', 'refuse']),
            ('date_from_new', '<=', today_end),
            ('date_to_new', '>=', today_start),
            ('type', '=', 'remove')
        ], ['employee_id'], ['employee_id'])
        result = dict.fromkeys(self.ids, False)
        for item in data:
            if item['employee_id_count'] >= 1:
                result[item['employee_id'][0]] = True
        for employee in self:
            employee.is_absent_totay = result[employee.id]

    @api.multi
    def _search_absent_employee(self, operator, value):
        today_date = datetime.datetime.utcnow().date()
        today_start = fields.Datetime.to_string(today_date)  # get the midnight of the current utc day
        today_end = fields.Datetime.to_string(today_date + relativedelta(hours=23, minutes=59, seconds=59))
        holidays = self.env['hr.holidays'].sudo().search([
            ('employee_id', '!=', False),
            ('state', 'not in', ['cancel', 'refuse']),
            ('date_from_new', '<=', today_end),
            ('date_to_new', '>=', today_start),
            ('type', '=', 'remove')
        ])
        return [('id', 'in', holidays.mapped('employee_id').ids)]


class Department(models.Model):
    _inherit = 'hr.department'


    @api.multi
    def _compute_leave_count(self):
        Holiday = self.env['hr.holidays']
        import datetime
        today_date = datetime.datetime.utcnow().date()
        today_start = fields.Datetime.to_string(today_date)  # get the midnight of the current utc day
        today_end = fields.Datetime.to_string(today_date+ relativedelta(hours=23, minutes=59, seconds=59))

        leave_data = Holiday.read_group(
            [('department_id', 'in', self.ids),
             ('state', '=', 'confirm'), ('type', '=', 'remove')],
            ['department_id'], ['department_id'])
        allocation_data = Holiday.read_group(
            [('department_id', 'in', self.ids),
             ('state', '=', 'confirm'), ('type', '=', 'add')],
            ['department_id'], ['department_id'])
        absence_data = Holiday.read_group(
            [('department_id', 'in', self.ids), ('state', 'not in', ['cancel', 'refuse']),
             ('date_from_new', '<=', today_end), ('date_to_new', '>=', today_start), ('type', '=', 'remove')],
            ['department_id'], ['department_id'])

        res_leave = dict((data['department_id'][0], data['department_id_count']) for data in leave_data)
        res_allocation = dict((data['department_id'][0], data['department_id_count']) for data in allocation_data)
        res_absence = dict((data['department_id'][0], data['department_id_count']) for data in absence_data)

        for department in self:
            department.leave_to_approve_count = res_leave.get(department.id, 0)
            department.allocation_to_approve_count = res_allocation.get(department.id, 0)
            department.absence_of_today = res_absence.get(department.id, 0)



class HrHolidaysImport(models.Model):
    _name = 'hr.holidays.import'
    _description = "Leaves Import"


    datas = fields.Binary(string='File Content')
    datas_fname = fields.Char('File path')
    state = fields.Selection([('draft', 'Draft'),('done', 'Imported'),('failed','Failed')], string='Status', default='draft')


    @api.multi
    def import_leaves_custom(self):
        datas_fname = self.datas_fname
        workbook = open_workbook(datas_fname)
        worksheet = workbook.sheet_by_index(0)
        hr_emp_obj = self.env['hr.employee']
        hr_holidays_obj = self.env['hr.holidays']
        for row in range(1, worksheet.nrows):
            print("row------",row)
            #column0 emp_code
            emp_code = worksheet.cell(row,0).value   
            hr_emp_id = hr_emp_obj.search([('emp_code', '=', emp_code)])
            manager_id = hr_emp_id.parent_id.id if hr_emp_id.parent_id else None
            user_id = hr_emp_id.user_id.id if hr_emp_id.user_id else None
            department_id = hr_emp_id.department_id.id if hr_emp_id.department_id else None
            if hr_emp_id.parent_id and hr_emp_id.parent_id.user_id:
                manager_user_id = hr_emp_id.parent_id.user_id.id
            else:
                manager_user_id = None
            #column1 name
            name = worksheet.cell(row,1).value #Leave Allocation 
            #column2 code
            code = worksheet.cell(row,2).value #leave code(PL)
            #column3 holiday_status_id
            holiday_status_id = worksheet.cell(row,3).value #(PL id)
            #column4 type
            type1 = worksheet.cell(row,4).value #type(add)
            #column5 state
            state = worksheet.cell(row,5).value #state(allocated)
            #column6 allocated
            allocated = worksheet.cell(row,6).value #allocated boolean(true)
            #column7 current_month
            current_month = worksheet.cell(row,7).value #current month(apr)
            #column8 number_of_days
            number_of_days = worksheet.cell(row,8).value #number of days(0)
            #column9 holiday_type
            holiday_type = worksheet.cell(row,9).value #holiday_type(employee)
            #column10 payslip_status
            payslip_status = worksheet.cell(row,10).value #payslip_status(false)
            #column11 first_approver_id
            first_approver_id = worksheet.cell(row,11).value #first_approver_id(1 admin)
            #column12 financial_year_id
            financial_year_id = worksheet.cell(row,12).value #financial_year_id(current 12)
            #column13 half_day_applicable
            half_day_applicable = worksheet.cell(row,13).value #half_day_Applicable(false)
            #column14 comp_off
            comp_off = worksheet.cell(row,14).value # comp_off(false)
            #column15 sandwich
            sandwich = worksheet.cell(row,15).value # sandwich(false)
            #column16 balanced_days_formula
            balanced_days_final = worksheet.cell(row,16).value #balanced_days_final
            #column18 to_be_enchashed
            to_be_encashed = worksheet.cell(row,18).value #to_be_encashed
            # if hr_emp_id and manager_id and user_id and department_id:
            if balanced_days_final < 0.5:
                print("0 leaves will not be imported")
            else:
                if hr_emp_id:
                    leaves_allotment = hr_holidays_obj.create(
                        {
                            'name': name,
                            'code': code,
                            'holiday_status_id': holiday_status_id,
                            'type': type1,
                            'state': state,
                            'allocated': allocated,
                            'employee_id' : hr_emp_id.id,
                            'manager_id': manager_id,
                            'current_month': current_month,
                            'number_of_days': number_of_days,
                            'holiday_type': holiday_type,
                            'payslip_status': payslip_status,
                            'user_id': user_id,
                            'department_id': department_id,
                            'manager_user_id': manager_user_id,
                            # 'leave_manager_id': leave_manager_id,
                            'first_approver_id': first_approver_id,
                            'financial_year_id': financial_year_id,
                            'half_day_applicable': half_day_applicable,
                            'comp_off': comp_off,
                            'sandwich': sandwich,                        
                            'total_days' : balanced_days_final,
                            'balanced_days' :balanced_days_final,
                            'to_be_encashed': to_be_encashed
                        })
                else:
                    print("emp doest not exists",emp_code)
        res = self.write({'state': 'done'})
        return res
