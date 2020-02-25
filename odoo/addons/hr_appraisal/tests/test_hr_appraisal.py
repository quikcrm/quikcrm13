# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestHrAppraisal(TransactionCase):
    """ Test used to check that when doing appraisal creation."""

    def setUp(self):
        super(TestHrAppraisal, self).setUp()
        self.HrEmployee = self.env['hr.employee']
        self.HrAppraisal = self.env['hr.appraisal']
        self.main_company = self.env.ref('base.main_company')

        group = self.env.ref('hr_appraisal.group_hr_appraisal_user').id
        self.user = self.env['res.users'].create({
            'name': 'Michael Hawkins',
            'login': 'test',
            'groups_id': [(6, 0, [group])],
        })

        self.hr_employee = self.HrEmployee.create(dict(
            name="Michael Hawkins",
            user_id=self.user.id,
            department_id=self.env.ref('hr.dep_rd').id,
            parent_id=self.env.ref('hr.employee_al').id,
            job_id=self.env.ref('hr.job_developer').id,
            work_location="Grand-Rosière",
            work_phone="+3281813700",
            work_email='michael@odoo.com',
            appraisal_by_manager=True,
            appraisal_manager_ids=[self.env.ref('hr.employee_al').id],
            appraisal_by_colleagues=True,
            appraisal_colleagues_ids=[self.env.ref('hr.employee_stw').id],
            appraisal_self=True,
            appraisal_date=date.today() + relativedelta(months=-12, days=5)
        ))
        self.env['ir.config_parameter'].sudo().set_param("hr_appraisal.appraisal_min_period", 6)
        self.env['ir.config_parameter'].sudo().set_param("hr_appraisal.appraisal_max_period", 12)

    def test_hr_appraisal(self):
        # I create a new Employee with appraisal configuration.

        # I run the scheduler
        self.HrEmployee.run_employee_appraisal()  # cronjob

        # I check whether new appraisal is created for above employee or not
        appraisals = self.HrAppraisal.search([('employee_id', '=', self.hr_employee.id)])
        self.assertTrue(appraisals, "Appraisal not created")

        # I start the appraisal process by click on "Start Appraisal" button.
        appraisals.button_send_appraisal()

        # I check that state is "Appraisal Sent".
        self.assertEqual(appraisals.state, 'pending', "appraisal should be 'Appraisal Sent' state")
        # I check that "Final Interview Date" is set or not.
        appraisals.write({'date_final_interview': str(date.today() + relativedelta(months=1))})
        self.assertTrue(appraisals.date_final_interview, "Interview Date is not created")
        # I check whether final interview meeting is created or not
        appraisals = self.HrAppraisal.search([('employee_id', '=', self.hr_employee.id)])
        self.assertTrue(appraisals.meeting_id, "Meeting is not created")
        # I close this Apprisal
        appraisals.write({'state': 'done'})
        # I check that state of Appraisal is done.
        self.assertEqual(appraisals.state, 'done', "Appraisal should be in done state")

    def test_appraisal_cron_on_employees_with_no_appraisal_date(self):
        # Appraisal date is not set when creating a new employee and this was causing the cron to never be executed on them
        hr_employee2 = self.HrEmployee.create({'name': "John Doe"})

        self.assertFalse(hr_employee2.appraisal_date, 'No appraisal date is set on a new employee')
        hr_employee2.run_employee_appraisal()
        self.assertEqual(hr_employee2.appraisal_date, date.today() + relativedelta(months=12))

    def test_request_appraisal_too_early(self):
        self.HrAppraisal.create({
            'employee_id': self.hr_employee.id,
            'date_close': date.today() + relativedelta(months=1),
        })

        with self.assertRaises(ValidationError):
            self.HrAppraisal.with_user(self.user.id).create({
                'employee_id': self.hr_employee.id,
                'date_close': date.today() + relativedelta(months=2),
            })

    def test_request_appraisal_too_early_2(self):
        # force date in the past
        query = """
            UPDATE hr_employee
            SET appraisal_date=%s
            WHERE id=%s;
        """
        self.env.cr.execute(query, (date.today() + relativedelta(months=11), self.hr_employee.id))
        self.HrEmployee.invalidate_cache(['appraisal_date'])

        self.hr_employee.periodic_appraisal_created = True

        self.HrEmployee.run_employee_appraisal()  # cronjob
        self.assertTrue(self.hr_employee.periodic_appraisal_created, False)
        self.assertEqual(self.hr_employee.appraisal_date, date.today() + relativedelta(months=11))
