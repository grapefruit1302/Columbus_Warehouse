from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class StockReceiptIncoming(models.Model):
    _inherit = 'stock.receipt.incoming'

    def action_done(self):
        """Розширюємо метод проведення для створення рухів залишків"""
        _logger.info(f"🚀 Початок проведення прихідної накладної {self.number}")
        
        # Спочатку стандартне проведення
        result = super().action_done()
        
        # Створюємо рухи залишків ПІСЛЯ проведення
        self._create_balance_movements()
        
        return result

    def _create_balance_movements(self):
        """Створює рухи залишків для всіх позицій накладної"""
        if 'stock.balance.movement' not in self.env:
            _logger.warning("⚠️ Модуль stock.balance.movement не знайдено!")
            return
        
        _logger.info(f"📦 Створення рухів залишків для накладної {self.number}")
        
        for line in self.line_ids:
            if line.qty > 0:
                self._create_balance_movement_for_line(line)

    def _create_balance_movement_for_line(self, line):
        """Створює рух залишків для конкретної позиції"""
        Movement = self.env['stock.balance.movement']
        
        # Збираємо серійні номери якщо є
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
            movement = Movement.create_movement(**movement_vals)
            _logger.info(f"✅ Створено рух залишків для {line.nomenclature_id.name}" + 
                        (f" з S/N: {serial_numbers}" if serial_numbers else ""))
            
            # Додаємо повідомлення в документ
            self.message_post(
                body=f'✅ Створено рух залишків для {line.nomenclature_id.name}' + 
                     (f' з серійними номерами' if serial_numbers else ''),
                message_type='notification'
            )
            
        except Exception as e:
            _logger.error(f"❌ Помилка створення руху залишків для {line.nomenclature_id.name}: {e}")
            self.message_post(
                body=f'❌ Помилка створення руху залишків для {line.nomenclature_id.name}: {e}',
                message_type='notification'
            )


class StockReceiptDisposal(models.Model):
    _inherit = 'stock.receipt.disposal'

    def action_done(self):
        """Розширюємо метод проведення для створення рухів залишків"""
        _logger.info(f"🚀 Початок проведення акта оприходування {self.number}")
        
        # Спочатку стандартне проведення
        result = super().action_done()
        
        # Створюємо рухи залишків ПІСЛЯ проведення
        self._create_balance_movements()
        
        return result

    def _create_balance_movements(self):
        """Створює рухи залишків для всіх позицій акта"""
        if 'stock.balance.movement' not in self.env:
            _logger.warning("⚠️ Модуль stock.balance.movement не знайдено!")
            return
        
        _logger.info(f"📦 Створення рухів залишків для акта {self.number}")
        
        for line in self.line_ids:
            if line.qty > 0:
                self._create_balance_movement_for_line(line)

    def _create_balance_movement_for_line(self, line):
        """Створює рух залишків для конкретної позиції"""
        Movement = self.env['stock.balance.movement']
        
        # Збираємо серійні номери якщо є
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
            movement = Movement.create_movement(**movement_vals)
            _logger.info(f"✅ Створено рух залишків для {line.nomenclature_id.name}" + 
                        (f" з S/N: {serial_numbers}" if serial_numbers else ""))
            
            self.message_post(
                body=f'✅ Створено рух залишків для {line.nomenclature_id.name}' + 
                     (f' з серійними номерами' if serial_numbers else ''),
                message_type='notification'
            )
            
        except Exception as e:
            _logger.error(f"❌ Помилка створення руху залишків для {line.nomenclature_id.name}: {e}")
            self.message_post(
                body=f'❌ Помилка створення руху залишків для {line.nomenclature_id.name}: {e}',
                message_type='notification'
            )