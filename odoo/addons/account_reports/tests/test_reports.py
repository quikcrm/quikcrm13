# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import date, datetime
import calendar
import time

from unittest.mock import patch

from odoo.tools.misc import formatLang
from odoo import fields

from odoo.addons.account_reports.tests.common import TestAccountReportsCommon2


class TestAccountReports(TestAccountReportsCommon2):

    def test_05_apply_date_filter(self):
        def patched_today(*args, **kwargs):
            return fields.Date.to_date('2018-12-11')

        with patch.object(fields.Date, 'context_today', patched_today):
            # Init options.
            report = self.env['account.report']
            report.filter_date = {
                'filter': 'last_month',
                'mode': 'range',
            }
            options = report._get_options(None)

            self.assertEqual(options['date']['date_from'], '2018-11-01')
            self.assertEqual(options['date']['date_to'], '2018-11-30')

    def test_06_apply_date_filter_with_timezone(self):
        self.env.user.tz = 'America/Mexico_City'
        original_context_today = fields.Date.context_today

        def patched_today(*args, **kwargs):
            timestamp = datetime(2019, 1, 1, 2, 0, 0)
            return original_context_today(self.env.user, timestamp)

        with patch.object(fields.Date, 'context_today', patched_today):
            # Init options.
            report = self.env['account.report']
            report.filter_date = {
                'filter': 'last_month',
                'mode': 'single',
            }
            options = report._get_options(None)

            today = fields.Date.to_date('2018-12-31')
            fiscal_date_to = self.env.company.compute_fiscalyear_dates(today)['date_to']

            target_day = calendar.monthrange(fiscal_date_to.year, fiscal_date_to.month - 1)[1]

            # New date in option should really be the month before
            expected_date = date(year=fiscal_date_to.year, month=fiscal_date_to.month - 1, day=target_day)
            expected_date = fields.Date.to_string(expected_date)

            self.assertEqual(options['date']['date_to'], expected_date)
