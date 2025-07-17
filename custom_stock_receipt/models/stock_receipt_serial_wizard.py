from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class StockReceiptSerialWizard(models.TransientModel):
    _name = 'stock.receipt.serial.wizard'
    _description = 'Wizard для введення серійних номерів'
    _inherit = ['stock.receipt.serial.wizard.base']

    # Специфічні поля для прихідної накладної
    receipt_id = fields.Many2one('stock.receipt.incoming', 'Прихідна накладна', required=True)
    selected_line_id = fields.Many2one('stock.receipt.incoming.line', 'Обрана позиція', required=True)
    serial_line_ids = fields.One2many('stock.receipt.serial.wizard.serial', 'wizard_id', 'Серійні номери')

    # Реалізація абстрактних методів
    def _get_document_field_name(self):
        return 'receipt_id'

    def _get_line_field_name(self):
        return 'selected_line_id'

    def _get_document_model(self):
        return 'stock.receipt.incoming'

    def _get_line_model(self):
        return 'stock.receipt.incoming.line'

    def _get_serial_line_model(self):
        return 'stock.receipt.serial.wizard.serial'

    def _get_balance_operation_type(self):
        return 'receipt'


class StockReceiptSerialWizardLine(models.TransientModel):
    _name = 'stock.receipt.serial.wizard.serial'
    _description = 'Лінія товарів з серійними номерами'
    _inherit = ['stock.receipt.serial.wizard.line.base']
 
    wizard_id = fields.Many2one('stock.receipt.serial.wizard', 'Wizard', required=True, ondelete='cascade')