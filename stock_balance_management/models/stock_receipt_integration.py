# stock_balance_management/models/stock_receipt_integration.py
# ВИПРАВЛЕННЯ: Уникаємо подвоєння залишків без зміни batch модуля

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class StockReceiptIncoming(models.Model):
    """Інтеграція з прихідними накладними"""
    _inherit = 'stock.receipt.incoming'

    def _do_posting(self, posting_time, custom_datetime=None):
        """Розширюємо метод проведення для оновлення залишків"""
        _logger.info(f"🔄 [BALANCE] Starting posting for receipt {self.number}")
        
        # Спочатку викликаємо super() щоб відпрацювали інші модулі (включаючи batch)
        result = super()._do_posting(posting_time, custom_datetime)
        
        # Перевіряємо чи залишки вже створені для цього документа
        existing_movements = self.env['stock.balance.movement'].search([
            ('document_reference', '=', self.number),
            ('operation_type', '=', 'receipt')
        ])
        
        if existing_movements:
            _logger.info(f"⚠️ [BALANCE] Movements already exist for {self.number}, skipping creation")
            return result
        
        # Створюємо залишки тільки якщо їх ще немає
        _logger.info(f"📦 [BALANCE] Creating balance movements for receipt {self.number}")
        for line in self.line_ids:
            try:
                self._create_balance_movement_for_line(line)
                _logger.info(f"✅ [BALANCE] Balance movement created for {line.nomenclature_id.name}")
            except Exception as e:
                _logger.error(f"❌ [BALANCE] Failed to create balance movement for {line.nomenclature_id.name}: {e}")
        
        return result

    def _create_balance_movement_for_line(self, line):
        """Створює рух залишків для позиції накладної"""
        if line.qty <= 0:
            _logger.warning(f"⚠️ Skipping line with qty <= 0: {line.nomenclature_id.name}")
            return
        
        # Отримуємо локацію (якщо не вказана, використовуємо основну локацію складу)
        location = line.location_id or self.warehouse_id.lot_stock_id
        
        # ДЕТАЛЬНИЙ АНАЛІЗ серійних номерів
        _logger.info(f"🔍 DETAILED SERIAL ANALYSIS for {line.nomenclature_id.name}:")
        _logger.info(f"   📋 line.serial_numbers: '{getattr(line, 'serial_numbers', 'FIELD_NOT_FOUND')}'")
        _logger.info(f"   🏷️ tracking_serial: {line.nomenclature_id.tracking_serial}")
        _logger.info(f"   📝 serial_numbers type: {type(getattr(line, 'serial_numbers', None))}")
        _logger.info(f"   📏 serial_numbers length: {len(getattr(line, 'serial_numbers', '')) if getattr(line, 'serial_numbers', None) else 0}")
        
        # Шукаємо партію (може бути створена batch модулем)
        batch = self.env['stock.batch'].search([
            ('source_document_type', '=', 'receipt'),
            ('source_document_number', '=', self.number),
            ('nomenclature_id', '=', line.nomenclature_id.id)
        ], limit=1)
        
        _logger.info(f"📦 Found batch for {line.nomenclature_id.name}: {batch.batch_number if batch else 'None'}")
        
        try:
            # ПОКРАЩЕНА логіка обробки серійних номерів
            serial_numbers_to_pass = None
            
            if hasattr(line, 'serial_numbers') and line.serial_numbers:
                # Очищаємо від зайвих пробілів та порожніх рядків
                cleaned_serials = line.serial_numbers.strip()
                if cleaned_serials:
                    if line.nomenclature_id.tracking_serial:
                        serial_numbers_to_pass = cleaned_serials
                        _logger.info(f"✅ PASSING cleaned serial numbers: '{serial_numbers_to_pass}'")
                        
                        # Додаткова інформація
                        serials_list = []
                        for line_serial in cleaned_serials.split('\n'):
                            for serial in line_serial.split(','):
                                serial = serial.strip()
                                if serial:
                                    serials_list.append(serial)
                        _logger.info(f"📊 Parsed serials list ({len(serials_list)} items): {serials_list}")
                    else:
                        _logger.warning(f"⚠️ Serial numbers exist but tracking_serial is FALSE for {line.nomenclature_id.name}")
                        _logger.warning(f"   📝 Please enable 'Облік по S/N' for this product!")
                else:
                    _logger.info(f"ℹ️ Serial numbers field exists but is empty after cleaning")
            else:
                _logger.info(f"ℹ️ No serial numbers for {line.nomenclature_id.name}")
            
            # Створюємо рух залишків
            _logger.info(f"🔧 Creating movement with serial_numbers: '{serial_numbers_to_pass}'")
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
                serial_numbers=serial_numbers_to_pass,
                company_id=self.company_id.id,
                date=self.posting_datetime,
            )
            
            _logger.info(f"✅ Created movement ID: {movement.id}")
            _logger.info(f"📝 Movement serial_numbers: '{movement.serial_numbers}'")
            
            # Перевіряємо чи серійні номери потрапили в залишки
            balance = self.env['stock.balance'].search([
                ('nomenclature_id', '=', line.nomenclature_id.id),
                ('location_type', '=', 'warehouse'),
                ('warehouse_id', '=', self.warehouse_id.id),
                ('batch_id', '=', batch.id if batch else False),
            ], limit=1)
            
            if balance:
                _logger.info(f"🎯 Found balance ID: {balance.id}")
                _logger.info(f"📋 Balance serial_numbers: '{balance.serial_numbers}'")
                if balance.serial_numbers:
                    _logger.info(f"✅ SUCCESS: Serial numbers are in balance!")
                else:
                    _logger.warning(f"⚠️ WARNING: Serial numbers NOT in balance!")
            else:
                _logger.warning(f"❌ No balance record found!")
            
            self.message_post(
                body=_('Створено рух залишків для %s: +%s %s') % (
                    line.nomenclature_id.name, 
                    line.qty, 
                    (line.selected_uom_id or line.product_uom_id).name
                ),
                message_type='notification'
            )
            
        except Exception as e:
            _logger.error(f"❌ ERROR creating balance movement for {line.nomenclature_id.name}: {e}")
            import traceback
            _logger.error(f"🔴 Traceback: {traceback.format_exc()}")
            self.message_post(
                body=_('Помилка оновлення залишків для %s: %s') % (line.nomenclature_id.name, str(e)),
                message_type='notification'
            )
            raise


class StockReceiptDisposal(models.Model):
    """Інтеграція з актами оприходування"""
    _inherit = 'stock.receipt.disposal'

    def _do_posting(self, posting_time, custom_datetime=None):
        """Розширюємо метод проведення для оновлення залишків"""
        _logger.info(f"🔄 [BALANCE] Starting posting for disposal {self.number}")
        
        # Спочатку викликаємо super() щоб відпрацювали інші модулі (включаючи batch)
        result = super()._do_posting(posting_time, custom_datetime)
        
        # Перевіряємо чи залишки вже створені для цього документа
        existing_movements = self.env['stock.balance.movement'].search([
            ('document_reference', '=', self.number),
            ('operation_type', '=', 'disposal')
        ])
        
        if existing_movements:
            _logger.info(f"⚠️ [BALANCE] Movements already exist for {self.number}, skipping creation")
            return result
        
        # Створюємо залишки тільки якщо їх ще немає
        _logger.info(f"📦 [BALANCE] Creating balance movements for disposal {self.number}")
        for line in self.line_ids:
            try:
                self._create_balance_movement_for_line(line)
                _logger.info(f"✅ [BALANCE] Balance movement created for {line.nomenclature_id.name}")
            except Exception as e:
                _logger.error(f"❌ [BALANCE] Failed to create balance movement for {line.nomenclature_id.name}: {e}")
        
        return result

    def _create_balance_movement_for_line(self, line):
        """Створює рух залишків для позиції акта"""
        if line.qty <= 0:
            _logger.warning(f"⚠️ Skipping line with qty <= 0: {line.nomenclature_id.name}")
            return
        
        # Отримуємо локацію (якщо не вказана, використовуємо основну локацію складу)
        location = line.location_id or self.warehouse_id.lot_stock_id
        
        # ДЕТАЛЬНИЙ АНАЛІЗ серійних номерів
        _logger.info(f"🔍 DETAILED SERIAL ANALYSIS for {line.nomenclature_id.name}:")
        _logger.info(f"   📋 line.serial_numbers: '{getattr(line, 'serial_numbers', 'FIELD_NOT_FOUND')}'")
        _logger.info(f"   🏷️ tracking_serial: {line.nomenclature_id.tracking_serial}")
        
        # Шукаємо партію (може бути створена batch модулем)
        batch = self.env['stock.batch'].search([
            ('source_document_type', '=', 'inventory'),
            ('source_document_number', '=', self.number),
            ('nomenclature_id', '=', line.nomenclature_id.id)
        ], limit=1)
        
        _logger.info(f"📦 Found batch for {line.nomenclature_id.name}: {batch.batch_number if batch else 'None'}")
        
        try:
            # ПОКРАЩЕНА логіка обробки серійних номерів
            serial_numbers_to_pass = None
            
            if line.serial_numbers:
                cleaned_serials = line.serial_numbers.strip()
                if cleaned_serials:
                    if line.nomenclature_id.tracking_serial:
                        serial_numbers_to_pass = cleaned_serials
                        _logger.info(f"✅ PASSING cleaned serial numbers: '{serial_numbers_to_pass}'")
                    else:
                        _logger.warning(f"⚠️ Serial numbers exist but tracking_serial is FALSE")
                else:
                    _logger.info(f"ℹ️ Serial numbers field exists but is empty after cleaning")
            else:
                _logger.info(f"ℹ️ No serial numbers for {line.nomenclature_id.name}")
            
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
                serial_numbers=serial_numbers_to_pass,
                company_id=self.company_id.id,
                date=self.posting_datetime,
            )
            
            _logger.info(f"✅ Created movement ID: {movement.id} with serial_numbers: '{movement.serial_numbers}'")
            
            self.message_post(
                body=_('Створено рух залишків для %s: +%s %s') % (
                    line.nomenclature_id.name, 
                    line.qty, 
                    (line.selected_uom_id or line.product_uom_id).name
                ),
                message_type='notification'
            )
            
        except Exception as e:
            _logger.error(f"❌ ERROR creating balance movement: {e}")
            import traceback
            _logger.error(f"🔴 Traceback: {traceback.format_exc()}")
            self.message_post(
                body=_('Помилка оновлення залишків для %s: %s') % (line.nomenclature_id.name, str(e)),
                message_type='notification'
            )
            raise