from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class StockReceiptIncoming(models.Model):
    _inherit = 'stock.receipt.incoming'

    def action_done(self):
        """Розширюємо метод проведення для створення рухів залишків"""
        # Спочатку стандартне проведення
        result = super().action_done()
        
        # Створюємо рухи залишків з серійними номерами
        for line in self.line_ids:
            if line.qty > 0:
                Movement = self.env['stock.balance.movement']
                
                serial_numbers = line.serial_numbers if line.tracking_serial else None
                
                movement_vals = {
                    'nomenclature_id': line.nomenclature_id.id,
                    'movement_type': 'in',
                    'operation_type': 'receipt',
                    'qty': line.qty,
                    'uom_id': line.selected_uom_id.id if line.selected_uom_id else line.nomenclature_id.base_uom_id.id,
                    'date': self.posting_datetime or fields.Datetime.now(),
                    'document_reference': f'Прихідна накладна {self.number}',
                    'serial_numbers': serial_numbers,
                    'company_id': self.company_id.id,
                    'location_to_type': 'warehouse',
                    'warehouse_to_id': self.warehouse_id.id,
                    'location_to_id': self.warehouse_id.lot_stock_id.id,
                }
                
                try:
                    Movement.create_movement(**movement_vals)
                    _logger.info(f"Створено рух залишків для {line.nomenclature_id.name}")
                except Exception as e:
                    _logger.error(f"Помилка створення руху залишків: {e}")
        
        return result


class StockReceiptDisposal(models.Model):
    _inherit = 'stock.receipt.disposal'

    def action_done(self):
        """Розширюємо метод проведення для створення рухів залишків"""
        # Спочатку стандартне проведення
        result = super().action_done()
        
        # Створюємо рухи залишків з серійними номерами
        for line in self.line_ids:
            if line.qty > 0:
                Movement = self.env['stock.balance.movement']
                
                serial_numbers = line.serial_numbers if line.tracking_serial else None
                
                movement_vals = {
                    'nomenclature_id': line.nomenclature_id.id,
                    'movement_type': 'in',
                    'operation_type': 'disposal',
                    'qty': line.qty,
                    'uom_id': line.selected_uom_id.id if line.selected_uom_id else line.nomenclature_id.base_uom_id.id,
                    'date': self.posting_datetime or fields.Datetime.now(),
                    'document_reference': f'Акт оприходування {self.number}',
                    'serial_numbers': serial_numbers,
                    'company_id': self.company_id.id,
                    'location_to_type': 'warehouse',
                    'warehouse_to_id': self.warehouse_id.id,
                    'location_to_id': self.warehouse_id.lot_stock_id.id,
                }
                
                try:
                    Movement.create_movement(**movement_vals)
                    _logger.info(f"Створено рух залишків для {line.nomenclature_id.name}")
                except Exception as e:
                    _logger.error(f"Помилка створення руху залишків: {e}")
        
        return result