# coding: utf-8
import base64
import logging
import os
import pytz
import socket
import re
from datetime import datetime
from hashlib import sha256
from odoo import _
from zeep import Client, Plugin
from zeep.exceptions import Fault
from zeep.wsse.username import UsernameToken

from lxml import etree

_logger = logging.getLogger(__name__)
# uncomment to enable logging of Zeep requests and responses
# logging.getLogger('zeep.transports').setLevel(logging.DEBUG)


class CarvajalException(Exception):
    pass

class CarvajalPlugin(Plugin):

    def egress(self, envelope, http_headers, operation, binding_options):
        self.log(envelope, 'carvajal_request')
        return envelope, http_headers

    def ingress(self, envelope, http_headers, operation):
        self.log(envelope, 'carvajal_response')
        return envelope, http_headers

    def log(self, xml, func):
        _logger.debug('%s with\n%s' % (func, etree.tostring(xml, encoding='utf-8', xml_declaration=True, pretty_print=True)))


class CarvajalRequest():
    def __init__(self, username, password, company, account, test_mode):
        self.username = username or ''
        self.password = password or ''
        self.company = company or ''
        self.account = account or ''

        token = self._create_wsse_header(self.username, self.password)
        self.client = Client('https://cenfinanciero%s.cen.biz/isows/InvoiceService?wsdl' % ('lab' if test_mode else ''), plugins=[CarvajalPlugin()], wsse=token)

    def _create_wsse_header(self, username, password):

        created = datetime.now()
        token = UsernameToken(username=username, password=sha256(password.encode()).hexdigest(), use_digest=True, created=created)

        return token

    def upload(self, filename, xml):
        try:
            response = self.client.service.Upload(fileName=filename, fileData=base64.b64encode(xml).decode(),
                                                  companyId=self.company, accountId=self.account)
        except Fault as fault:
            _logger.error(fault)
            raise CarvajalException(fault)
        except socket.timeout as e:
            _logger.error(e)
            raise CarvajalException(_('Connection to Carvajal timed out. Their API is probably down.'))

        return {
            'message': response.status,
            'transactionId': response.transactionId,
        }

    def download(self, document_prefix, document_number, document_type):
        try:
            response = self.client.service.Download(documentPrefix=document_prefix, documentNumber=document_number,
                                                    documentType=document_type, resourceType='PDF,SIGNED_XML',
                                                    companyId=self.company, accountId=self.account)
        except Fault as fault:
            _logger.error(fault)
            raise CarvajalException(fault)

        return {
            'message': response.status,
            'zip_b64': base64.b64decode(response.downloadData),
        }

    def check_status(self, transactionId):
        try:
            response = self.client.service.DocumentStatus(transactionId=transactionId,
                                                          companyId=self.company, accountId=self.account)
        except Fault as fault:
            _logger.error(fault)
            raise CarvajalException(fault)

        return {
            'status': response.processStatus,
            'errorMessage': response.errorMessage if hasattr(response, 'errorMessage') else '',
            'legalStatus': response.legalStatus if hasattr(response, 'legalStatus') else '',
            'governmentResponseDescription': response.governmentResponseDescription if hasattr(response, 'governmentResponseDescription') else '',
        }
