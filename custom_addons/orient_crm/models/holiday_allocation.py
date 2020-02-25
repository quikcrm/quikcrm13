

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


class HolidayAllocation(models.Model):
    _name = "holiday.allocation"
    _description = "Leave Allocation"


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

    holiday_status_id = fields.Many2one("hr.holidays.status", string="Leave Type")
    code = fields.Char('Code')
    total_days = fields.Float('Duration', copy=False, help='Number of days of the leave request according to your working schedule.')
    employee_id = fields.Many2one('hr.employee', string='Employee', index=True)
    employee_code = fields.Integer('Employee Code')
    manager_id = fields.Many2one('hr.employee', string='Manager')
    department_id = fields.Many2one('hr.department', string='Department')
    site_id = fields.Many2one('site.master', string='Site')
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
    allocation_line_ids = fields.One2many('hr.holidays', 'holiday_allocation_id', ondelete='restrict')
    allocation_line_temp_ids = fields.One2many('hr.holidays', 'holiday_allocation_temp_id', ondelete='restrict')
    leave_manager_id = fields.Many2one('res.users', string='Leave Manager', default=_default_leave_manager_id)
    comp_off = fields.Boolean('Comp Off')
    comp_off_date = fields.Date('Comp Off Date')
    results = fields.Char(string='Results')
    show_temp_ids = fields.Boolean(string='Show temp ids?')



    @api.onchange('holiday_status_id')
    def onchange_holiday_status_id(self):
        data = {}
        holidays_obj = self.env['hr.holidays']
        holiday_stat_id = self.env['hr.holidays.status'].search([('code','=','CO')])
        if self.holiday_status_id.name==holiday_stat_id.name:
            data['comp_off'] = True
        else:
            data['comp_off'] = False
        if self.holiday_status_id:
            data['code'] = self.holiday_status_id.code
        else:
            data['code'] = None
        if self.holiday_status_id == holiday_stat_id:
            data['total_days'] = 1
        data['results'] = None
        data['show_temp_ids'] = True
        return {'value':data}


    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        self.employee_code = self.employee_id.emp_code
        self.manager_id = self.employee_id and self.employee_id.parent_id
        self.department_id = self.employee_id.department_id
        self.site_id = self.employee_id.site_master_id
        self.results = None
        self.show_temp_ids = True


    @api.multi
    def search_allocated_leaves(self):
        holidays_obj = self.env['hr.holidays']
        # delete existing searched ids
        existing_searched_records = holidays_obj.search([('holiday_allocation_id','=',self.id)])
        existing_searched_records.write({'holiday_allocation_id': None})
        # finding the allocated leaves
        domain = [
                  ('type','=','add'),
                  ('state','=','allocated'),
                  ('holiday_status_id','=',self.holiday_status_id.id),
                  ('code','=',self.code),
                  ('employee_id','=',self.employee_id.id),
                  ('financial_year_id','=',self.financial_year_id.id),
                 ]
        if self.comp_off_date:
            domain.append(('comp_off_date','=',self.comp_off_date))
        allocated_ids = holidays_obj.search(domain)
        # writing the allocated leaves in lines
        allocated_ids.write({'holiday_allocation_id': self.id})
        res = self.write({'show_temp_ids':False,'results':str(len(allocated_ids))+' record(s) fetched'})
        return res


    @api.multi
    def update_allocated_leaves(self):
        # leaves to be allocated cannot be 0 
        res = None
        if self.total_days == 0:
            raise ValidationError(_('Cannot add 0 leaves. Please enter some leaves!'))
        holidays_obj = self.env['hr.holidays']
        # delete existing searched ids
        existing_searched_records = holidays_obj.search([('holiday_allocation_id','=',self.id)])
        existing_searched_records.write({'holiday_allocation_id': None})
        # finding the allocated leaves
        domain = [
                    ('type','=','add'),
                    ('state','=','allocated'),
                    ('holiday_status_id','=',self.holiday_status_id.id),
                    ('code','=',self.code),
                    ('employee_id','=',self.employee_id.id),
                    ('manager_id','=',self.manager_id.id),
                    ('department_id','=',self.department_id.id),
                    ('financial_year_id','=',self.financial_year_id.id),
                 ]
        allocated_ids = holidays_obj.search(domain)
        # updating the allocated ids with the given duration
        if allocated_ids:
            for each_allocated_id in allocated_ids:
                total_days = each_allocated_id.total_days
                balanced_days = each_allocated_id.balanced_days
                each_allocated_id.write(
                    {
                        'holiday_allocation_id': self.id,
                        'total_days': each_allocated_id.total_days+self.total_days,
                        'balanced_days': each_allocated_id.balanced_days+self.total_days,
                        'number_of_days': 0,
                        'current_month': self.current_month
                    })
            res = self.write({'show_temp_ids':False,'results':str(self.total_days)+' '+self.code+'s'+' '+'added for employee '+self.employee_id.name})
        return res


    @api.multi
    def allocate_leaves(self):
        # check if the selected leave type is allocable------------------------------------------------------------------------------
        if self.holiday_status_id.allocable == False:
            raise UserError(_("%s are not allocable") % (self.holiday_status_id.name))
        #----------------------------------------------------------------------------------------------------------------------------

        # check if the employee is confirmed before allocating-----------------------------------------------------------------------
        if self.holiday_status_id.applicable_to == 'confirmed':
            if self.employee_id.position_type == 'probation':
                raise UserError(_("%s are allocable only for confirmed employees.") % (self.holiday_status_id.name))
        #----------------------------------------------------------------------------------------------------------------------------

        # leaves to be allocated cannot be 0 
        if self.total_days == 0:
            raise ValidationError(_('Cannot allocate 0 leaves. Please enter some leaves!'))

        # comp off date mandatory for comp-off leave type
        if self.code=='CO' and not self.comp_off_date:
            raise ValidationError(_('Please enter the comp off date to be allocated !'))

        # check if comp-off is already allocated for the selected comp-off date------------------------------------------------------
        existing_co_date_id = self.env['hr.holidays'].search([('comp_off_date', '=', self.comp_off_date),('allocated', '=', True),('id', '!=', self.id)])
        if self.holiday_status_id.code == 'CO' and existing_co_date_id and existing_co_date_id!=self.id:
            raise UserError(_("Compensatory off is already allocated against %s !") % (self.comp_off_date))
        #----------------------------------------------------------------------------------------------------------------------------

        # check if comp-off being allocated is for future date-----------------------------------------------------------------------
        if self.comp_off_date:
            comp_off_date = datetime.strptime(self.comp_off_date, '%Y-%m-%d')
            if comp_off_date > datetime.now():
                raise UserError(_('Cannot allocate future date for Compensatory off!'))
        #----------------------------------------------------------------------------------------------------------------------------  

        holidays_obj = self.env['hr.holidays']
        # delete existing searched ids
        existing_searched_records = holidays_obj.search([('holiday_allocation_id','=',self.id)])
        existing_searched_records.write({'holiday_allocation_id': None})

        # allocating leaves(creating a record)
        holidays_obj.create(
            {
                'type': 'add',
                'name': 'Leave Allocation',
                'code': self.code,
                'holiday_status_id': self.holiday_status_id.id, 
                'employee_id': self.employee_id.id,
                'employee_code': self.employee_id.emp_code,
                'manager_id': self.manager_id.id,
                'manager_user_id': self.manager_id.user_id.id,
                'user_id': self.employee_id.user_id.id,
                'leave_manager_id': self.leave_manager_id.id,
                'department_id': self.department_id.id,
                'holiday_type': 'employee',
                'first_approver_id': 1,
                'total_days': self.total_days,
                'balanced_days': self.total_days,
                'number_of_days': 0,
                'payslip_status': False,
                'half_day_applicable': False,
                'comp_off': self.comp_off,
                'comp_off_date': self.comp_off_date,
                'current_month': self.current_month,
                'financial_year_id': self.financial_year_id.id,
                'state': 'allocated',
                'allocated': True,
                'holiday_allocation_id': self.id
            })

        # allocate = holidays_obj.action_allocate()
        # print("allocate---",allocate)
        res = self.write({'show_temp_ids':False,'results':str(self.total_days)+' '+self.code+'(s)'+' '+'allocated to employee '+self.employee_id.name})
        return res



class HolidayAllocationLogs(models.Model):
    _name = "holiday.allocation.logs"
    _description = "monthly leave allocation error logs" 
    _order = "date_a_time desc"
    _rec_name = 'error_logs'

    date_a_time = fields.Datetime('Date')
    error_logs = fields.Text('Error Logs')



class Holidays(models.Model):
    _inherit = "hr.holidays"
    _order = "type desc, date_from_new desc"


    def allocate_monthly_leaves(self):
        allocation_logs_obj = self.env['holiday.allocation.logs']
        try:
            year_obj = self.env['year.master']
            allocable_holiday_ids = self.env['hr.holidays.status'].search([('code','=','PL')])
            month = datetime.today().month
            if month == 1:
                current_month = 'jan'
                months_lapsed = 9
            if month == 2:
                current_month = 'feb'
                months_lapsed = 10
            if month == 3:
                current_month = 'mar'
                months_lapsed = 11
            if month == 4:
                current_month = 'apr'
                months_lapsed = 0
            if month == 5:
                current_month = 'may'
                months_lapsed = 1
            if month == 6:
                current_month = 'june'
                months_lapsed = 2
            if month == 7:
                current_month = 'july'
                months_lapsed = 3
            if month == 8:
                current_month = 'aug'
                months_lapsed = 4
            if month == 9:
                current_month = 'sept'
                months_lapsed = 5
            if month == 10:
                current_month = 'oct'
                months_lapsed = 6
            if month == 11:
                current_month = 'nov'
                months_lapsed = 7
            if month == 12:
                current_month = 'dec'
                months_lapsed = 8
            for each_allocable_holiday_id in allocable_holiday_ids:
                print("leaves----------------",each_allocable_holiday_id.code)
                if each_allocable_holiday_id.allocability == 'pro_rata':
                    number_of_leaves = each_allocable_holiday_id.maximum_allocation/12
                else:
                    number_of_leaves = [each_allocable_holiday_id.maximum_allocation-(months_lapsed * (each_allocable_holiday_id.maximum_allocation/12))]
                if each_allocable_holiday_id.applicable_to == 'confirmed':
                    applicability = 'confirm'
                else:
                    applicability = 'probation'
                employee_ids = self.env['hr.employee'].search([('active','=',True),('position_type','=',applicability)])
                for each_emp_id in employee_ids:
                    print("employee---------------------",each_emp_id.name)
                    existing_leave_id = self.search([('type','=','add'),('code','=', each_allocable_holiday_id.code),('employee_id','=', each_emp_id.id)])
                    if existing_leave_id:
                        print("existing leaves update by 1",existing_leave_id)
                        existing_leave_id.write(
                            {
                                'total_days': existing_leave_id.total_days+number_of_leaves,
                                'balanced_days': existing_leave_id.balanced_days+number_of_leaves,
                                'current_month': current_month
                            })
                    else:
                        users = []
                        user_id = None
                        query = """SELECT id FROM ir_module_category WHERE name = 'Leaves';"""
                        self.env.cr.execute(query)
                        category_id = self.env.cr.dictfetchall()
                        leave_manager_group = self.env['res.groups'].search([('category_id','=',category_id[0].get('id')),('name','=','Manager')])
                        for user in leave_manager_group.users:
                            if user.id != 1:
                                users.append(user.id)
                        if users:
                            user_id = users[0]
                        leave_manager_id = user_id
                        financial_year_id = False
                        curr_date = datetime.today()
                        year = curr_date.year
                        year_master_ids = year_obj.search([('name','ilike',str(year))])
                        for each_year_master_id in year_master_ids:
                            start_date = datetime.strptime(each_year_master_id.start_date,'%Y-%m-%d')
                            end_date = datetime.strptime(each_year_master_id.end_date,'%Y-%m-%d')
                            if curr_date >= start_date and curr_date <= end_date:
                                financial_year_id = each_year_master_id.id
                        if not financial_year_id:
                            raise AccessError("Financial Year not defined!")
                        if each_allocable_holiday_id.allocability == 'pro_rata':
                            number_of_leaves = each_allocable_holiday_id.maximum_allocation/12
                        else:
                            number_of_leaves = [each_allocable_holiday_id.maximum_allocation-(months_lapsed * (each_allocable_holiday_id.maximum_allocation/12))]
                        print("new leaves allocated",number_of_leaves)
                        holiday_vals = {
                                'type': 'add',
                                'name': 'Leave Allocation',
                                'code': each_allocable_holiday_id.code,
                                'holiday_status_id': each_allocable_holiday_id.id,
                                'employee_id': each_emp_id.id,
                                'manager_id': each_emp_id.parent_id.id,
                                'manager_user_id': each_emp_id.parent_id.user_id.id,
                                'user_id': each_emp_id.user_id.id,
                                'leave_manager_id': leave_manager_id,
                                'department_id': each_emp_id.department_id.id,
                                'holiday_type': 'employee',
                                'first_approver_id': 1,
                                'total_days': number_of_leaves,
                                'balanced_days': number_of_leaves,
                                'number_of_days': 0,
                                'payslip_status': False,
                                'half_day_applicable': False,
                                'comp_off': False,
                                'comp_off_date': None,
                                'current_month': current_month,
                                'financial_year_id': financial_year_id,
                                'state': 'allocated',
                                'allocated': True
                            }
                        self.create(holiday_vals)
        except Exception as e:
            print("logs------",e)
            res = allocation_logs_obj.create(
                {
                    'error_logs': e,
                    'date_a_time': datetime.now()
                })
            return res
        return True



    def compensatory_off_allocation(self):
        allocation_logs_obj = self.env['holiday.allocation.logs']
        try:
        # if True:
            hr_emp_obj = self.env['hr.employee']
            year_obj = self.env['year.master']
            curr_date = datetime.today()
            previous_date = curr_date-timedelta(days=1)
            yesterday = previous_date.strftime('%Y-%m-%d')
            print("yesterday----------------------",yesterday,type(yesterday))
            yesterday_day = datetime.strptime(yesterday, "%Y-%m-%d").day
            this_year = datetime.now().year
            yesterday_month = datetime.strptime(yesterday, "%Y-%m-%d").month
            this_month = datetime.today().month
            sat_holidays = {}
            co_holiday_id = self.env['hr.holidays.status'].search([('code','=','CO')])
            if co_holiday_id.applicable_to == 'confirmed':
                emp_ids = hr_emp_obj.search([('active','=',True),('position_type','=','confirm')]).ids
            else:
                emp_ids = hr_emp_obj.search([('active','=',True)]).ids
            # emp_ids = [16981]
            for each_emp_id in emp_ids:
                allocate_comp_off = False
                each_emp_id = hr_emp_obj.browse(each_emp_id)
                # find out the attendance record for current employee for yesterday
                attendance_id = self.env['hr.attendance'].search([('employee_id','=',each_emp_id.id),('attendance_date','=',yesterday),('employee_code','=',each_emp_id.emp_code)])
                if attendance_id:
                    print("attendance_id",attendance_id)
                    # check if employee has PH for yesterday and worked_hours are greater than or equal to 6
                    if each_emp_id.holiday_ids:
                        for each_holiday in each_emp_id.holiday_ids:
                            if each_holiday.holiday_date == yesterday:
                                if attendance_id.worked_hours >= 6:
                                    allocate_comp_off = True
                    # check if the employee site is flexishift or no
                    if each_emp_id.site_master_id:
                        # for branch employee, check if yesterday was weekoff and worked_hours are greater than or equal to 6
                        if not each_emp_id.site_master_id.flexishift:
                            weekoffs = each_emp_id.site_master_id.weekoffs
                            weekday = previous_date.weekday()
                            # if yesterday was saturday
                            if weekday == 5:
                                # check if the saturday is off or working
                                if weekoffs == 'all' or weekoffs == 'saturday_weekoff': # all the saturdays are off
                                    if attendance_id.worked_hours >= 6:
                                        allocate_comp_off = True
                                elif weekoffs == 'no': # all the saturdays are working
                                    pass
                                else:
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
                                    secondforth_saturdays = sat_holidays.get(yesterday_month)
                                    print("secondforth_saturdays",secondforth_saturdays)
                                    if weekoffs == '2_4':
                                        if yesterday_day in secondforth_saturdays: # this saturday comes under secondforth saturdays
                                            if attendance_id.worked_hours >= 6:
                                                allocate_comp_off = True
                                    else: # weekoffs = 1_3_5:
                                        if yesterday_day not in secondforth_saturdays: # this saturday comes under firstthirdfifth saturdays
                                            if attendance_id.worked_hours >= 6:
                                                allocate_comp_off = True
                            # if yesterday was sunday
                            if weekday == 6:
                                # check if the sunday is off or working
                                if weekoffs == 'saturday_weekoff': # only saturday weekoff i.e sunday is working
                                    pass
                                else:# sunday is off
                                    if attendance_id.worked_hours >= 6:
                                        allocate_comp_off = True
                        else: # for FMS employee, check if shift is 'WO' and worked_hours are greater than or equal to 6
                            if attendance_id.shift.name == 'WO' and attendance_id.worked_hours >= 6:
                                allocate_comp_off = True
                    print("allocate_comp_off",allocate_comp_off)
                    if allocate_comp_off == True:
                        # get_leave manager_id
                        users = []
                        user_id = None
                        query = """SELECT id FROM ir_module_category WHERE name = 'Leaves';"""
                        self.env.cr.execute(query)
                        category_id = self.env.cr.dictfetchall()
                        leave_manager_group = self.env['res.groups'].search([('category_id','=',category_id[0].get('id')),('name','=','Manager')])
                        for user in leave_manager_group.users:
                            if user.id != 1:
                                users.append(user.id)
                        if users:
                            user_id = users[0]
                        leave_manager_id = user_id
                        # get current month
                        if this_month == 1:
                            current_month = 'jan'
                        if this_month == 2:
                            current_month = 'feb'
                        if this_month == 3:
                            current_month = 'mar'
                        if this_month == 4:
                            current_month = 'apr'
                        if this_month == 5:
                            current_month = 'may'
                        if this_month == 6:
                            current_month = 'june'
                        if this_month == 7:
                            current_month = 'july'
                        if this_month == 8:
                            current_month = 'aug'
                        if this_month == 9:
                            current_month = 'sept'
                        if this_month == 10:
                            current_month = 'oct'
                        if this_month == 11:
                            current_month = 'nov'
                        if this_month == 12:
                            current_month = 'dec'
                        # get financial_year_id
                        financial_year_id = False
                        year_master_ids = year_obj.search([('name','ilike',str(this_year))])
                        for each_year_master_id in year_master_ids:
                            start_date = datetime.strptime(each_year_master_id.start_date,'%Y-%m-%d')
                            end_date = datetime.strptime(each_year_master_id.end_date,'%Y-%m-%d')
                            if curr_date >= start_date and curr_date <= end_date:
                                financial_year_id = each_year_master_id.id
                        if not financial_year_id:
                            raise AccessError("Financial Year not defined!")
                        comp_off_vals = {
                                'type': 'add',
                                'name': 'Leave Allocation',
                                'code': 'CO',
                                'holiday_status_id': co_holiday_id.id, 
                                'employee_id': each_emp_id.id,
                                'employee_code': each_emp_id.emp_code,
                                'manager_id': each_emp_id.parent_id.id,
                                'manager_user_id': each_emp_id.parent_id.user_id.id,
                                'user_id': each_emp_id.user_id.id,
                                'leave_manager_id': leave_manager_id,
                                'department_id': each_emp_id.department_id.id,
                                'holiday_type': 'employee',
                                'first_approver_id': 1,
                                'total_days': 1,
                                'balanced_days': 1,
                                'number_of_days': 0,
                                'payslip_status': False,
                                'half_day_applicable': False,
                                'comp_off': True,
                                'comp_off_date': yesterday,
                                'current_month': current_month,
                                'financial_year_id': financial_year_id,
                                'state': 'allocated',
                                'allocated': True,
                            }
                        self.create(comp_off_vals)
        except Exception as e:
            print("logs------",e)
            log = "comp off log:"+str(e)
            res = allocation_logs_obj.create(
                {
                    'error_logs': log,
                    'date_a_time': datetime.now()
                })
            return res               
        return True