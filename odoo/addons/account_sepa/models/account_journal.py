# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round, float_repr, DEFAULT_SERVER_DATE_FORMAT

import random
import re
import time
from lxml import etree

def sanitize_communication(communication):
    """ Returns a sanitized version of the communication given in parameter,
        so that:
            - it contains only latin characters
            - it does not contain any //
            - it does not start or end with /
            - it is maximum 140 characters long
        (these are the SEPA compliance criteria)
    """
    communication = communication[:140]
    while '//' in communication:
        communication = communication.replace('//', '/')
    if communication.startswith('/'):
        communication = communication[1:]
    if communication.endswith('/'):
        communication = communication[:-1]
    communication = re.sub('[^-A-Za-z0-9/?:().,\'+ ]', '', communication)
    return communication

class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _default_outbound_payment_methods(self):
        vals = super(AccountJournal, self)._default_outbound_payment_methods()
        return vals + self.env.ref('account_sepa.account_payment_method_sepa_ct')

    @api.model
    def _enable_sepa_ct_on_bank_journals(self):
        """ Enables sepa credit transfer payment method on bank journals. Called upon module installation via data file.
        """
        sepa_ct = self.env.ref('account_sepa.account_payment_method_sepa_ct')
        euro = self.env.ref('base.EUR')
        if self.env.company.currency_id == euro:
            domain = ['&', ('type', '=', 'bank'), '|', ('currency_id', '=', euro.id), ('currency_id', '=', False)]
        else:
            domain = ['&', ('type', '=', 'bank'), ('currency_id', '=', euro.id)]
        for bank_journal in self.search(domain):
            bank_journal.write({'outbound_payment_method_ids': [(4, sepa_ct.id, None)]})

    def create_iso20022_credit_transfer(self, payments, batch_booked=False, sct_generic=False):
        """
            This method creates the body of the XML file for the SEPA document.
            It returns the content of the XML file.
        """
        pain_version = self.company_id.sepa_pain_version
        Document = self._get_document(pain_version)
        CstmrCdtTrfInitn = etree.SubElement(Document, "CstmrCdtTrfInitn")

        # Create the GrpHdr XML block
        GrpHdr = etree.SubElement(CstmrCdtTrfInitn, "GrpHdr")
        MsgId = etree.SubElement(GrpHdr, "MsgId")
        val_MsgId = str(int(time.time() * 100))[-10:]
        val_MsgId = sanitize_communication(self.company_id.name[-15:]) + val_MsgId
        val_MsgId = str(random.random()) + val_MsgId
        val_MsgId = val_MsgId[-30:]
        MsgId.text = val_MsgId
        CreDtTm = etree.SubElement(GrpHdr, "CreDtTm")
        CreDtTm.text = time.strftime("%Y-%m-%dT%H:%M:%S")
        NbOfTxs = etree.SubElement(GrpHdr, "NbOfTxs")
        val_NbOfTxs = str(len(payments))
        if len(val_NbOfTxs) > 15:
            raise ValidationError(_("Too many transactions for a single file."))
        if not self.bank_account_id.bank_bic:
            raise UserError(_("There is no Bank Identifier Code recorded for bank account '%s' of journal '%s'") % (self.bank_account_id.acc_number, self.name))
        NbOfTxs.text = val_NbOfTxs
        CtrlSum = etree.SubElement(GrpHdr, "CtrlSum")
        CtrlSum.text = self._get_CtrlSum(payments)
        GrpHdr.append(self._get_InitgPty(sct_generic))

        # Create one PmtInf XML block per execution date
        payments_date_wise = {}
        for payment in payments:
            if payment['payment_date'] not in payments_date_wise:
                payments_date_wise[payment['payment_date']] = []
            payments_date_wise[payment['payment_date']].append(payment)
        count = 0
        for payment_date, payments_list in payments_date_wise.items():
            count += 1
            PmtInf = etree.SubElement(CstmrCdtTrfInitn, "PmtInf")
            PmtInfId = etree.SubElement(PmtInf, "PmtInfId")
            PmtInfId.text = (val_MsgId + str(self.id) + str(count))[-30:]
            PmtMtd = etree.SubElement(PmtInf, "PmtMtd")
            PmtMtd.text = 'TRF'
            BtchBookg = etree.SubElement(PmtInf, "BtchBookg")
            BtchBookg.text = str(batch_booked).lower()
            NbOfTxs = etree.SubElement(PmtInf, "NbOfTxs")
            NbOfTxs.text = str(len(payments_list))
            CtrlSum = etree.SubElement(PmtInf, "CtrlSum")
            CtrlSum.text = self._get_CtrlSum(payments_list)
            PmtInf.append(self._get_PmtTpInf(sct_generic))
            ReqdExctnDt = etree.SubElement(PmtInf, "ReqdExctnDt")
            ReqdExctnDt.text = fields.Date.to_string(payment_date)
            PmtInf.append(self._get_Dbtr(sct_generic))
            PmtInf.append(self._get_DbtrAcct())
            DbtrAgt = etree.SubElement(PmtInf, "DbtrAgt")
            FinInstnId = etree.SubElement(DbtrAgt, "FinInstnId")
            BIC = etree.SubElement(FinInstnId, "BIC")
            BIC.text = self.bank_account_id.bank_bic.replace(' ', '')

            # One CdtTrfTxInf per transaction
            for payment in payments_list:
                PmtInf.append(self._get_CdtTrfTxInf(PmtInfId, payment, sct_generic))

        return etree.tostring(Document, pretty_print=True, xml_declaration=True, encoding='utf-8')


    def _get_document(self, pain_version):
        if pain_version == 'pain.001.001.03.ch.02':
            Document = self._create_pain_001_001_03_ch_document()
        elif pain_version == 'pain.001.003.03':
            Document = self._create_pain_001_003_03_document()
        else:
            Document = self._create_pain_001_001_03_document()

        return Document

    def _create_pain_001_001_03_document(self):
        """ Create a sepa credit transfer file that follows the European Payment Councile generic guidelines (pain.001.001.03)

            :param doc_payments: recordset of account.payment to be exported in the XML document returned
        """
        Document = self._create_iso20022_document('pain.001.001.03')
        return Document

    def _create_pain_001_001_03_ch_document(self):
        """ Create a sepa credit transfer file that follows the swiss specific guidelines, as established
            by SIX Interbank Clearing (pain.001.001.03.ch.02)

            :param doc_payments: recordset of account.payment to be exported in the XML document returned
        """
        Document = etree.Element("Document", nsmap={
            None: "http://www.six-interbank-clearing.com/de/pain.001.001.03.ch.02.xsd",
            'xsi': "http://www.w3.org/2001/XMLSchema-instance"})
        return Document

    def _create_pain_001_003_03_document(self):
        """ Create a sepa credit transfer file that follows the german specific guidelines, as established
            by the German Bank Association (Deutsche Kreditwirtschaft) (pain.001.003.03)

            :param doc_payments: recordset of account.payment to be exported in the XML document returned
        """
        Document = self._create_iso20022_document('pain.001.003.03')
        return Document

    def _create_iso20022_document(self, pain_version):
        return etree.Element("Document", nsmap={
            None: "urn:iso:std:iso:20022:tech:xsd:%s" % (pain_version,),
            'xsi': "http://www.w3.org/2001/XMLSchema-instance"})

    def _get_CtrlSum(self, payments):
        return float_repr(float_round(sum(payment['amount'] for payment in payments), 2), 2)

    def _get_InitgPty(self, sct_generic=False):
        InitgPty = etree.Element("InitgPty")
        InitgPty.extend(self._get_company_PartyIdentification32(sct_generic, org_id=True, postal_address=False))
        return InitgPty

    def _get_company_PartyIdentification32(self, sct_generic=False, org_id=True, postal_address=True):
        """ Returns a PartyIdentification32 element identifying the current journal's company
        """
        ret = []
        company = self.company_id
        name_length = sct_generic and 35 or 70

        Nm = etree.Element("Nm")
        Nm.text = sanitize_communication(company.sepa_initiating_party_name[:name_length])
        ret.append(Nm)

        if postal_address and company.partner_id.city and company.partner_id.country_id.code:
            ret.append(self._get_PstlAdr(company.partner_id))

        if org_id and company.sepa_orgid_id:
            Id = etree.Element("Id")
            OrgId = etree.SubElement(Id, "OrgId")
            Othr = etree.SubElement(OrgId, "Othr")
            _Id = etree.SubElement(Othr, "Id")
            _Id.text = sanitize_communication(company.sepa_orgid_id)
            if company.sepa_orgid_issr:
                Issr = etree.SubElement(Othr, "Issr")
                Issr.text = sanitize_communication(company.sepa_orgid_issr)
            ret.append(Id)

        return ret

    def _get_PmtTpInf(self, sct_generic=False):
        PmtTpInf = etree.Element("PmtTpInf")
        InstrPrty = etree.SubElement(PmtTpInf, "InstrPrty")
        InstrPrty.text = 'NORM'

        if not sct_generic:
            SvcLvl = etree.SubElement(PmtTpInf, "SvcLvl")
            Cd = etree.SubElement(SvcLvl, "Cd")
            Cd.text = 'SEPA'

        return PmtTpInf

    def _get_Dbtr(self, sct_generic=False):
        Dbtr = etree.Element("Dbtr")
        Dbtr.extend(self._get_company_PartyIdentification32(sct_generic,org_id=lambda: not sct_generic, postal_address=True))
        return Dbtr

    def _get_DbtrAcct(self):
        DbtrAcct = etree.Element("DbtrAcct")
        Id = etree.SubElement(DbtrAcct, "Id")
        IBAN = etree.SubElement(Id, "IBAN")
        IBAN.text = self.bank_account_id.sanitized_acc_number
        Ccy = etree.SubElement(DbtrAcct, "Ccy")
        Ccy.text = self.currency_id and self.currency_id.name or self.company_id.currency_id.name

        return DbtrAcct

    def _get_PstlAdr(self, partner_id):
        PstlAdr = etree.Element("PstlAdr")
        Ctry = etree.SubElement(PstlAdr, "Ctry")
        Ctry.text = partner_id.country_id.code
        if partner_id.street:
            AdrLine = etree.SubElement(PstlAdr, "AdrLine")
            AdrLine.text = sanitize_communication(partner_id.street[:70])
        if partner_id.zip and partner_id.city:
            AdrLine = etree.SubElement(PstlAdr, "AdrLine")
            AdrLine.text = sanitize_communication((partner_id.zip + " " + partner_id.city)[:70])
        return PstlAdr

    def _get_CdtTrfTxInf(self, PmtInfId, payment, sct_generic):
        CdtTrfTxInf = etree.Element("CdtTrfTxInf")
        PmtId = etree.SubElement(CdtTrfTxInf, "PmtId")
        InstrId = etree.SubElement(PmtId, "InstrId")
        InstrId.text = sanitize_communication(payment['name'][:35])
        EndToEndId = etree.SubElement(PmtId, "EndToEndId")
        EndToEndId.text = (PmtInfId.text + str(payment['id']))[-30:]
        Amt = etree.SubElement(CdtTrfTxInf, "Amt")

        currency_id = self.env['res.currency'].search([('id', '=', payment['currency_id'])], limit=1)
        journal_id = self.env['account.journal'].search([('id', '=', payment['journal_id'])], limit=1)
        val_Ccy = currency_id and currency_id.name or journal_id.company_id.currency_id.name
        val_InstdAmt = float_repr(float_round(payment['amount'], 2), 2)
        max_digits = val_Ccy == 'EUR' and 11 or 15
        if len(re.sub('\.', '', val_InstdAmt)) > max_digits:
            raise ValidationError(_("The amount of the payment '%s' is too high. The maximum permitted is %s.") % (payment['name'], str(9) * (max_digits - 3) + ".99"))
        InstdAmt = etree.SubElement(Amt, "InstdAmt", Ccy=val_Ccy)
        InstdAmt.text = val_InstdAmt
        CdtTrfTxInf.append(self._get_ChrgBr(sct_generic))

        partner_id = self.env['res.partner'].search([('id', '=', payment['partner_id'])], limit=1)
        if partner_id.bank_ids:
            bank_id = partner_id.bank_ids[0]
        elif partner_id.parent_id and partner_id.parent_id.bank_ids:
            bank_id = partner_id.parent_id.bank_ids[0]
        else:
            raise UserError(_('A partner has not a bank id.'))

        CdtTrfTxInf.append(self._get_CdtrAgt(bank_id, sct_generic))
        Cdtr = etree.SubElement(CdtTrfTxInf, "Cdtr")
        Nm = etree.SubElement(Cdtr, "Nm")
        Nm.text = sanitize_communication((bank_id.acc_holder_name or partner_id.name)[:70])
        if partner_id.city and partner_id.country_id.code:
            Cdtr.append(self._get_PstlAdr(partner_id))
        if payment['payment_type'] == 'transfer':
            CdtTrfTxInf.append(self._get_CdtrAcct(payment['destination_bank_account_id']))
        else:
            CdtTrfTxInf.append(self._get_CdtrAcct(bank_id, sct_generic))
        val_RmtInf = self._get_RmtInf(payment)
        if val_RmtInf is not False:
            CdtTrfTxInf.append(val_RmtInf)
        return CdtTrfTxInf

    def _get_ChrgBr(self, sct_generic):
        ChrgBr = etree.Element("ChrgBr")
        ChrgBr.text = sct_generic and "SHAR" or "SLEV"
        return ChrgBr

    def _get_CdtrAgt(self, bank_account, sct_generic):
        CdtrAgt = etree.Element("CdtrAgt")
        FinInstnId = etree.SubElement(CdtrAgt, "FinInstnId")
        val_BIC = bank_account.bank_bic
        if val_BIC:
            BIC = etree.SubElement(FinInstnId, "BIC")
            BIC.text = val_BIC.replace(' ', '')
        elif not sct_generic:
            raise UserError(_("There is no Bank Identifier Code recorded for bank account '%s'") % bank_account.acc_number)

        return CdtrAgt

    def _get_CdtrAcct(self, bank_account, sct_generic):
        if not sct_generic and (not bank_account.acc_type or not bank_account.acc_type == 'iban'):
            raise UserError(_("The account %s, linked to partner '%s', is not of type IBAN.\nA valid IBAN account is required to use SEPA features.") % (bank_account.acc_number, bank_account.partner_id.name))

        CdtrAcct = etree.Element("CdtrAcct")
        Id = etree.SubElement(CdtrAcct, "Id")
        if sct_generic and bank_account.acc_type != 'iban':
            Othr = etree.SubElement(Id, "Othr")
            _Id = etree.SubElement(Othr, "Id")
            acc_number = bank_account.acc_number
            # CH case when when we have non-unique account numbers
            if " " in bank_account.sanitized_acc_number and " " in bank_account.acc_number:
                acc_number = bank_account.acc_number.split(" ")[0]
            _Id.text = acc_number
        else:
            IBAN = etree.SubElement(Id, "IBAN")
            IBAN.text = bank_account.sanitized_acc_number

        return CdtrAcct

    def _get_RmtInf(self, payment):
        if not payment['communication']:
            return False
        RmtInf = etree.Element("RmtInf")
        Ustrd = etree.SubElement(RmtInf, "Ustrd")
        Ustrd.text = sanitize_communication(payment['communication'])
        return RmtInf
