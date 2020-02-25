# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _,api
import requests
import logging
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError, Warning
_logger = logging.getLogger(__name__)

class ConfirmWizard(models.TransientModel):
    _name = 'confirm.wizard'
    _description = 'Wizard for Confirmation'

    @api.multi
    def action_yes(self):
        print('------',self._context)
        
    @api.multi
    def action_no(self):
        print('------',self._context)
        