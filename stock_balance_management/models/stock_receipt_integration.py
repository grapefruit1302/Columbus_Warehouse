# stock_balance_management/models/stock_receipt_integration.py
# ВИПРАВЛЕННЯ: Уникаємо подвоєння залишків без зміни batch модуля

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class StockReceiptIncoming(models.Model):
    """
    Інтеграція з прихідними накладними для оновлення залишків (унікнення дублювання рухів).
    """
    _inherit = 'stock.receipt.incoming'

    def _do_posting(self, posting_time, custom_datetime=None):
        """
        Розширює метод проведення для оновлення залишків після проведення документа.
        """
        _logger.info(f"[BALANCE] Starting posting for receipt {self.number}")
        result = super()._do_posting(posting_time, custom_datetime)
        # Перевіряємо, чи рухи вже створені для цього документа
        existing_movements = self.env['stock.balance.movement'].search([
            ('document_reference', '=', self.number),
            ('operation_type', '=', 'receipt')
        ])
        if existing_movements:
            _logger.info(f"[BALANCE] Movements already exist for {self.number}, skipping creation")
            return result
        _logger.info(f"[BALANCE] Creating balance movements for receipt {self.number}")
        for line in self.line_ids:
            try:
                self._create_balance_movement_for_line(line)
                _logger.info(f"[BALANCE] Balance movement created for {line.nomenclature_id.name}")
            except Exception as e:
                _logger.error(f"[BALANCE] Failed to create balance movement for {line.nomenclature_id.name}: {e}")
        return result

    def _create_balance_movement_for_line(self, line):
        """
        Створює рух залишків для позиції накладної (з урахуванням серійних номерів).
        """
        if line.qty <= 0:
            _logger.warning(f"Skipping line with qty <= 0: {line.nomenclature_id.name}")
            return
        location = line.location_id or self.warehouse_id.lot_stock_id
        batch = self.env['stock.batch'].search([
            ('source_document_type', '=', 'receipt'),
            ('source_document_number', '=', self.number),
            ('nomenclature_id', '=', line.nomenclature_id.id)
        ], limit=1)
        serial_numbers_to_pass = None
        if line.serial_numbers:
            cleaned_serials = line.serial_numbers.strip()
            if cleaned_serials and line.nomenclature_id.tracking_serial:
                serial_numbers_to_pass = cleaned_serials
        try:
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
            _logger.info(f"Created movement ID: {movement.id} with serial_numbers: '{movement.serial_numbers}'")
            self.message_post(
                body=_('Створено рух залишків для %s: +%s %s') % (
                    line.nomenclature_id.name, 
                    line.qty, 
                    (line.selected_uom_id or line.product_uom_id).name
                ),
                message_type='notification'
            )
        except Exception as e:
            _logger.error(f"ERROR creating balance movement for {line.nomenclature_id.name}: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            self.message_post(
                body=_('Помилка оновлення залишків для %s: %s') % (line.nomenclature_id.name, str(e)),
                message_type='notification'
            )
            raise

class StockReceiptDisposal(models.Model):
    """
    Інтеграція з актами оприходування для оновлення залишків (унікнення дублювання рухів).
    """
    _inherit = 'stock.receipt.disposal'

    def _do_posting(self, posting_time, custom_datetime=None):
        """
        Розширює метод проведення для оновлення залишків після проведення документа.
        """
        _logger.info(f"[BALANCE] Starting posting for disposal {self.number}")
        result = super()._do_posting(posting_time, custom_datetime)
        existing_movements = self.env['stock.balance.movement'].search([
            ('document_reference', '=', self.number),
            ('operation_type', '=', 'disposal')
        ])
        if existing_movements:
            _logger.info(f"[BALANCE] Movements already exist for {self.number}, skipping creation")
            return result
        _logger.info(f"[BALANCE] Creating balance movements for disposal {self.number}")
        for line in self.line_ids:
            try:
                self._create_balance_movement_for_line(line)
                _logger.info(f"[BALANCE] Balance movement created for {line.nomenclature_id.name}")
            except Exception as e:
                _logger.error(f"[BALANCE] Failed to create balance movement for {line.nomenclature_id.name}: {e}")
        return result

    def _create_balance_movement_for_line(self, line):
        """
        Створює рух залишків для позиції акта (з урахуванням серійних номерів).
        """
        if line.qty <= 0:
            _logger.warning(f"Skipping line with qty <= 0: {line.nomenclature_id.name}")
            return
        location = line.location_id or self.warehouse_id.lot_stock_id
        batch = self.env['stock.batch'].search([
            ('source_document_type', '=', 'inventory'),
            ('source_document_number', '=', self.number),
            ('nomenclature_id', '=', line.nomenclature_id.id)
        ], limit=1)
        serial_numbers_to_pass = None
        if line.serial_numbers:
            cleaned_serials = line.serial_numbers.strip()
            if cleaned_serials and line.nomenclature_id.tracking_serial:
                serial_numbers_to_pass = cleaned_serials
        try:
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
            _logger.info(f"Created movement ID: {movement.id} with serial_numbers: '{movement.serial_numbers}'")
            self.message_post(
                body=_('Створено рух залишків для %s: +%s %s') % (
                    line.nomenclature_id.name, 
                    line.qty, 
                    (line.selected_uom_id or line.product_uom_id).name
                ),
                message_type='notification'
            )
        except Exception as e:
            _logger.error(f"ERROR creating balance movement: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            self.message_post(
                body=_('Помилка оновлення залишків для %s: %s') % (line.nomenclature_id.name, str(e)),
                message_type='notification'
            )
            raise