from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class StockReceiptIncoming(models.Model):
    """Інтеграція з прихідними накладними"""
    _inherit = 'stock.receipt.incoming'

    def action_confirm(self):
        """Розширюємо метод підтвердження для оновлення залишків"""
        _logger.info(f"Starting confirmation for receipt {self.number}")
        
        # Спочатку стандартне підтвердження
        result = super().action_confirm()
        
        # Оновлюємо залишки для кожної позиції ПІСЛЯ підтвердження
        _logger.info(f"Creating balance movements for receipt {self.number}")
        for line in self.line_ids:
            try:
                self._create_balance_movement_for_line(line)
                _logger.info(f"Balance movement created for {line.nomenclature_id.name}")
            except Exception as e:
                _logger.error(f"Failed to create balance movement for {line.nomenclature_id.name}: {e}")
        
        return result

    def _create_balance_movement_for_line(self, line):
        """Створює рух залишків для позиції накладної"""
        if line.qty <= 0:
            _logger.warning(f"Skipping line with qty <= 0: {line.nomenclature_id.name}")
            return
        
        # Отримуємо локацію (якщо не вказана, використовуємо основну локацію складу)
        location = line.location_id or self.warehouse_id.lot_stock_id
        
        # Шукаємо партію для ВСІХ товарів, не тільки з серійними номерами
        batch = self.env['stock.batch'].search([
            ('source_document_type', '=', 'receipt'),
            ('source_document_number', '=', self.number),
            ('nomenclature_id', '=', line.nomenclature_id.id)
        ], limit=1)
        
        _logger.info(f"Found batch for {line.nomenclature_id.name}: {batch.batch_number if batch else 'None'}")
        
        try:
            # Створюємо рух залишків
            movement = self.env['stock.balance.movement'].create_movement(
                nomenclature_id=line.nomenclature_id.id,
                qty=line.qty,
                movement_type='in',
                operation_type='receipt',
                location_to_type='warehouse',
                warehouse_to_id=self.warehouse_id.id,
                location_to_id=location.id,
                batch_id=batch.id if batch else None,
                uom_id=line.selected_uom_id.id or line.product_uom_id.id,
                document_reference=self.number,
                notes=f'Прихідна накладна {self.number}',
                serial_numbers=line.serial_numbers if line.tracking_serial else None,
                company_id=self.company_id.id,
                date=self.posting_datetime,
            )
            
            _logger.info(f"Created balance movement: {movement.id}")
            
            self.message_post(
                body=_('Створено рух залишків для %s: +%s %s') % (
                    line.nomenclature_id.name, 
                    line.qty, 
                    (line.selected_uom_id or line.product_uom_id).name
                ),
                message_type='notification'
            )
            
        except Exception as e:
            _logger.error(f"Помилка створення руху залишків для {line.nomenclature_id.name}: {e}")
            self.message_post(
                body=_('Помилка оновлення залишків для %s: %s') % (line.nomenclature_id.name, str(e)),
                message_type='notification'
            )
            # Викидаємо помилку далі, щоб не приховувати проблему
            raise


class StockReceiptDisposal(models.Model):
    """Інтеграція з актами оприходування"""
    _inherit = 'stock.receipt.disposal'

    def action_confirm(self):
        """Розширюємо метод підтвердження для оновлення залишків"""
        _logger.info(f"Starting confirmation for disposal {self.number}")
        
        # Спочатку стандартне підтвердження
        result = super().action_confirm()
        
        # Оновлюємо залишки для кожної позиції ПІСЛЯ підтвердження
        _logger.info(f"Creating balance movements for disposal {self.number}")
        for line in self.line_ids:
            try:
                self._create_balance_movement_for_line(line)
                _logger.info(f"Balance movement created for {line.nomenclature_id.name}")
            except Exception as e:
                _logger.error(f"Failed to create balance movement for {line.nomenclature_id.name}: {e}")
        
        return result

    def _create_balance_movement_for_line(self, line):
        """Створює рух залишків для позиції акта"""
        if line.qty <= 0:
            _logger.warning(f"Skipping line with qty <= 0: {line.nomenclature_id.name}")
            return
        
        # Отримуємо локацію (якщо не вказана, використовуємо основну локацію складу)
        location = line.location_id or self.warehouse_id.lot_stock_id
        
        # Шукаємо партію для цієї позиції
        batch = self.env['stock.batch'].search([
            ('source_document_type', '=', 'inventory'),
            ('source_document_number', '=', self.number),
            ('nomenclature_id', '=', line.nomenclature_id.id)
        ], limit=1)
        
        _logger.info(f"Found batch for {line.nomenclature_id.name}: {batch.batch_number if batch else 'None'}")
        
        try:
            # Створюємо рух залишків
            movement = self.env['stock.balance.movement'].create_movement(
                nomenclature_id=line.nomenclature_id.id,
                qty=line.qty,
                movement_type='in',
                operation_type='disposal',
                location_to_type='warehouse',
                warehouse_to_id=self.warehouse_id.id,
                location_to_id=location.id,
                batch_id=batch.id if batch else None,
                uom_id=line.selected_uom_id.id or line.product_uom_id.id,
                document_reference=self.number,
                notes=f'Акт оприходування {self.number}',
                serial_numbers=line.serial_numbers if line.tracking_serial else None,
                company_id=self.company_id.id,
                date=self.posting_datetime,
            )
            
            _logger.info(f"Created balance movement: {movement.id}")
            
            self.message_post(
                body=_('Створено рух залишків для %s: +%s %s') % (
                    line.nomenclature_id.name, 
                    line.qty, 
                    (line.selected_uom_id or line.product_uom_id).name
                ),
                message_type='notification'
            )
            
        except Exception as e:
            _logger.error(f"Помилка створення руху залишків для {line.nomenclature_id.name}: {e}")
            self.message_post(
                body=_('Помилка оновлення залишків для %s: %s') % (line.nomenclature_id.name, str(e)),
                message_type='notification'
            )
            # Викидаємо помилку далі, щоб не приховувати проблему  
            raise