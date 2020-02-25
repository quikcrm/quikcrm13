# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import _, api, models
from odoo.tools.misc import format_date


class L10nARVatBook(models.AbstractModel):

    _name = "l10n_ar.vat.book"
    _inherit = "account.report"
    _description = "Argentinian VAT Book"

    filter_date = {'date_from': '', 'date_to': '', 'filter': 'this_month'}
    filter_all_entries = False

    def _get_columns_name(self, options):
        return [
            {'name': _("Date"), 'class': 'date'},
            {'name': _("Document")},
            {'name': _("Name")},
            {'name': _("Vat Cond.")},
            {'name': _("VAT")},
            {'name': _('Taxed'), 'class': 'number'},
            {'name': _('Not Taxed'), 'class': 'number'},
            {'name': _('VAT 2,5%'), 'class': 'number'},
            {'name': _('VAT 5%'), 'class': 'number'},
            {'name': _('VAT 10,5%'), 'class': 'number'},
            {'name': _('VAT 21%'), 'class': 'number'},
            {'name': _('VAT 27%'), 'class': 'number'},
            {'name': _('Other Taxes'), 'class': 'number'},
            {'name': _('Total'), 'class': 'number'},
        ]

    @api.model
    def _get_report_name(self):
        journal_type = self.env.context.get('journal_type')
        # when printing report there is no key on context
        return {'sale': _('Sales VAT book'), 'purchase': _('Purchases VAT book')}.get(journal_type, _('VAT book'))

    @api.model
    def _get_lines(self, options, line_id=None):
        context = self.env.context
        journal_type = context.get('journal_type', 'sale')
        company_ids = context.get('company_ids')

        lines = []
        line_id = 0

        if journal_type == 'purchase':
            sign = 1.0
        else:
            sign = -1.0

        totals = {}.fromkeys(['taxed', 'not_taxed', 'vat_25', 'vat_5', 'vat_10', 'vat_21', 'vat_27', 'other_taxes', 'total'], 0)
        domain = [('journal_id.type', '=', journal_type), ('journal_id.l10n_latam_use_documents', '=', True),
                  ('company_id', 'in', company_ids)]
        state = context.get('state')
        if state and state.lower() != 'all':
            domain += [('state', '=', state)]
        if context.get('date_to'):
            domain += [('date', '<=', context['date_to'])]
        if context.get('date_from'):
            domain += [('date', '>=', context['date_from'])]
        for rec in self.env['account.ar.vat.line'].search_read(domain):
            taxed = rec['base_25'] + rec['base_5'] + rec['base_10'] + rec['base_21'] + rec['base_27']
            other_taxes = rec['other_taxes']
            totals['taxed'] += taxed
            totals['not_taxed'] += rec['not_taxed']
            totals['vat_25'] += rec['vat_25']
            totals['vat_5'] += rec['vat_5']
            totals['vat_10'] += rec['vat_10']
            totals['vat_21'] += rec['vat_21']
            totals['vat_27'] += rec['vat_27']
            totals['other_taxes'] += other_taxes
            totals['total'] += rec['total']

            if rec['type'] in ['in_invoice', 'in_refund']:
                caret_type = 'account.invoice.in'
            elif rec['type'] in ['out_invoice', 'out_refund']:
                caret_type = 'account.invoice.out'
            else:
                caret_type = 'account.move'
            lines.append({
                'id': rec['id'],
                'name': format_date(self.env, rec['invoice_date']),
                'class': 'date',
                'level': 2,
                'model': 'account.ar.vat.line',
                'caret_options': caret_type,
                'columns': [
                    {'name': rec['move_name']},
                    {'name': rec['partner_name']},
                    {'name': rec['afip_responsibility_type_name']},
                    {'name': rec['cuit']},
                    {'name': self.format_value(sign * taxed)},
                    {'name': self.format_value(sign * rec['not_taxed'])},
                    {'name': self.format_value(sign * rec['vat_25'])},
                    {'name': self.format_value(sign * rec['vat_5'])},
                    {'name': self.format_value(sign * rec['vat_10'])},
                    {'name': self.format_value(sign * rec['vat_21'])},
                    {'name': self.format_value(sign * rec['vat_27'])},
                    {'name': self.format_value(sign * other_taxes)},
                    {'name': self.format_value(sign * rec['total'])},
                ],
            })
            line_id += 1

        lines.append({
            'id': 'total',
            'name': _('Total'),
            'class': 'o_account_reports_domain_total',
            'level': 0,
            'columns': [
                {'name': ''},
                {'name': ''},
                {'name': ''},
                {'name': ''},
                {'name': self.format_value(sign * totals['taxed'])},
                {'name': self.format_value(sign * totals['not_taxed'])},
                {'name': self.format_value(sign * totals['vat_25'])},
                {'name': self.format_value(sign * totals['vat_5'])},
                {'name': self.format_value(sign * totals['vat_10'])},
                {'name': self.format_value(sign * totals['vat_21'])},
                {'name': self.format_value(sign * totals['vat_27'])},
                {'name': self.format_value(sign * totals['other_taxes'])},
                {'name': self.format_value(sign * totals['total'])},
            ],
        })
        return lines
