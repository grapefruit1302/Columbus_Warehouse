from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class StockDisposalSerialWizard(models.TransientModel):
    _name = 'stock.disposal.serial.wizard'
    _description = 'Wizard для введення серійних номерів в акт оприходування'
    _inherit = ['stock.receipt.serial.wizard.base']

    # Специфічні поля для акта оприходування
    disposal_id = fields.Many2one('stock.receipt.disposal', 'Акт оприходування', required=True)
    selected_line_id = fields.Many2one('stock.receipt.disposal.line', 'Обрана позиція', required=True)
    serial_line_ids = fields.One2many('stock.disposal.serial.wizard.serial', 'wizard_id', 'Серійні номери')

    # Реалізація абстрактних методів
    def _get_document_field_name(self):
        return 'disposal_id'

    def _get_line_field_name(self):
        return 'selected_line_id'

    def _get_document_model(self):
        return 'stock.receipt.disposal'

    def _get_line_model(self):
        return 'stock.receipt.disposal.line'

    def _get_serial_line_model(self):
        return 'stock.disposal.serial.wizard.serial'

    def _get_balance_operation_type(self):
        return 'disposal'

class StockDisposalSerialWizardLine(models.TransientModel):
    _name = 'stock.disposal.serial.wizard.serial'
    _description = 'Лінія товарів з серійними номерами'
    _inherit = ['stock.receipt.serial.wizard.line.base']
 
    wizard_id = fields.Many2one('stock.disposal.serial.wizard', 'Wizard', required=True, ondelete='cascade')