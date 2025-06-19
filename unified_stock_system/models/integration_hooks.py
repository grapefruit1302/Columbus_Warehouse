"""
Хуки для інтеграції існуючих модулів з централізованою системою залишків
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


# Розширення для custom_stock_receipt модулів
class StockReceiptIncoming(models.Model):
    _inherit = 'stock.receipt.incoming'
    
    def _do_posting(self, posting_time, custom_datetime=None):
        """Розширюємо метод проведення для оновлення централізованих залишків"""
        result = super()._do_posting(posting_time, custom_datetime)
        
        # Оновлюємо централізовані залишки для кожної позиції
        for line in self.line_ids:
            try:
                self.env['stock.warehouse.inventory'].update_from_receipt_incoming(line)
            except Exception as e:
                _logger.error(f"Помилка оновлення залишків для прихідної накладної {self.number}: {e}")
        
        return result


class StockReceiptDisposal(models.Model):
    _inherit = 'stock.receipt.disposal'
    
    def _do_posting(self, posting_time, custom_datetime=None):
        """Розширюємо метод проведення для оновлення централізованих залишків"""
        result = super()._do_posting(posting_time, custom_datetime)
        
        # Оновлюємо централізовані залишки для кожної позиції
        for line in self.line_ids:
            try:
                self.env['stock.warehouse.inventory'].update_from_receipt_disposal(line)
            except Exception as e:
                _logger.error(f"Помилка оновлення залишків для акта оприходування {self.number}: {e}")
        
        return result


class StockReceiptReturn(models.Model):
    _inherit = 'stock.receipt.return'
    
    def _do_posting(self, posting_time, custom_datetime=None):
        """Розширюємо метод проведення для оновлення централізованих залишків"""
        result = super()._do_posting(posting_time, custom_datetime)
        
        # Оновлюємо централізовані залишки для кожної позиції
        for line in self.line_ids:
            try:
                self.env['stock.warehouse.inventory'].update_from_receipt_return(line)
            except Exception as e:
                _logger.error(f"Помилка оновлення залишків для повернення {self.number}: {e}")
        
        return result


# Розширення для stock_transfer модуля
class StockTransferLine(models.Model):
    _inherit = 'stock.transfer.line'
    
    def _compute_available_nomenclature(self):
        """Оновлена версія - тепер використовує централізовані залишки"""
        for line in self:
            transfer = line.transfer_id
            
            if not transfer.transfer_type:
                line.available_nomenclature_ids = False
                continue
            
            # Отримуємо доступні товари з централізованих залишків
            available_stock = self._get_available_stock_from_warehouse_inventory()
            
            # Витягуємо унікальні номенклатури
            nomenclature_ids = available_stock.mapped('nomenclature_id').ids
            line.available_nomenclature_ids = [(6, 0, nomenclature_ids)]
    
    def _get_available_stock_from_warehouse_inventory(self):
        """Отримує доступні залишки з централізованої моделі"""
        transfer = self.transfer_id
        
        # Базовий домен
        domain = [
            ('qty_on_hand', '>', 0),
            ('active', '=', True),
            ('company_id', '=', transfer.company_id.id)
        ]
        
        # Додаємо умови залежно від типу переміщення
        if transfer.transfer_type == 'warehouse':
            domain.append(('warehouse_id', '=', transfer.warehouse_from_id.id))
        elif transfer.transfer_type == 'warehouse_employee':
            domain.append(('warehouse_id', '=', transfer.warehouse_from_id.id))
        elif transfer.transfer_type == 'employee_warehouse':
            # Для працівників поки що повертаємо порожній результат
            # Тут можна додати логіку для обліку товарів у працівників
            return self.env['stock.warehouse.inventory'].browse([])
        elif transfer.transfer_type == 'employee':
            # Між працівниками - поки що порожній результат
            return self.env['stock.warehouse.inventory'].browse([])
        
        return self.env['stock.warehouse.inventory'].search(domain)
    
    def _compute_available_batches(self):
        """Показує доступні партії для вибраної номенклатури"""
        for line in self:
            if not line.nomenclature_id:
                line.available_batches = "Оберіть товар"
                continue
            
            available_stock = self._get_available_stock_for_nomenclature()
            
            if not available_stock:
                line.available_batches = "Товар недоступний"
                continue
            
            # Формуємо інформацію про доступні партії
            batch_info = []
            for stock in available_stock:
                batch_name = stock.batch_name or "Без партії"
                batch_info.append(f"{batch_name}: {stock.qty_on_hand} {stock.uom_id.name}")
            
            line.available_batches = "; ".join(batch_info)
    
    def _get_available_stock_for_nomenclature(self):
        """Отримує залишки для конкретної номенклатури"""
        if not self.nomenclature_id:
            return self.env['stock.warehouse.inventory'].browse([])
        
        transfer = self.transfer_id
        
        domain = [
            ('nomenclature_id', '=', self.nomenclature_id.id),
            ('qty_on_hand', '>', 0),
            ('active', '=', True),
            ('company_id', '=', transfer.company_id.id)
        ]
        
        # Додаємо склад для переміщень зі складу
        if transfer.transfer_type in ['warehouse', 'warehouse_employee']:
            domain.append(('warehouse_id', '=', transfer.warehouse_from_id.id))
        
        return self.env['stock.warehouse.inventory'].search(domain)
    
    def _validate_stock_availability(self):
        """Перевіряє доступність товару в конкретній партії"""
        if not self.nomenclature_id or self.qty <= 0:
            return
        
        transfer = self.transfer_id
        
        # Шукаємо конкретний залишок
        domain = [
            ('nomenclature_id', '=', self.nomenclature_id.id),
            ('company_id', '=', transfer.company_id.id),
            ('active', '=', True)
        ]
        
        # Додаємо партію
        if self.lot_batch:
            domain.append(('batch_name', '=', self.lot_batch))
        else:
            domain.append(('batch_name', '=', False))
        
        # Додаємо склад для переміщень зі складу
        if transfer.transfer_type in ['warehouse', 'warehouse_employee']:
            domain.append(('warehouse_id', '=', transfer.warehouse_from_id.id))
        
        stock_record = self.env['stock.warehouse.inventory'].search(domain, limit=1)
        
        if not stock_record:
            raise ValidationError(
                f"Товар {self.nomenclature_id.name} "
                f"в партії '{self.lot_batch or 'Без партії'}' "
                f"відсутній на складі"
            )
        
        if stock_record.qty_on_hand < self.qty:
            raise ValidationError(
                f"Недостатньо товару {self.nomenclature_id.name} "
                f"в партії '{self.lot_batch or 'Без партії'}'. "
                f"Доступно: {stock_record.qty_on_hand} {stock_record.uom_id.name}, "
                f"потрібно: {self.qty} {self.selected_uom_id.name}"
            )
    
    def _process_transfer_movement(self):
        """Виконує рух товару при переміщенні"""
        self.ensure_one()
        
        # Списуємо з джерела
        self._subtract_from_source()
        
        # Додаємо в пункт призначення
        self._add_to_destination()
    
    def _subtract_from_source(self):
        """Списує товар з джерела"""
        transfer = self.transfer_id
        
        if transfer.transfer_type not in ['warehouse', 'warehouse_employee']:
            # Для переміщень від працівників поки що пропускаємо
            return
        
        # Знаходимо запис залишку
        domain = [
            ('warehouse_id', '=', transfer.warehouse_from_id.id),
            ('nomenclature_id', '=', self.nomenclature_id.id),
            ('company_id', '=', transfer.company_id.id),
            ('active', '=', True)
        ]
        
        if self.lot_batch:
            domain.append(('batch_name', '=', self.lot_batch))
        else:
            domain.append(('batch_name', '=', False))
        
        stock_record = self.env['stock.warehouse.inventory'].search(domain, limit=1)
        
        if not stock_record:
            raise ValidationError(f"Не знайдено залишок для списання: {self.nomenclature_id.name}")
        
        # Списуємо кількість
        stock_record._update_quantities({
            'qty_on_hand': self.qty,
            'operation_type': 'subtract',
            'source_document_type': 'transfer',
            'source_document_number': transfer.number,
            'last_movement_date': transfer.posting_datetime,
        })
    
    def _add_to_destination(self):
        """Додає товар в пункт призначення"""
        transfer = self.transfer_id
        
        if transfer.transfer_type not in ['warehouse', 'employee_warehouse']:
            # Для переміщень до працівників поки що пропускаємо
            return
        
        # Створюємо або оновлюємо запис залишку в пункті призначення
        vals = {
            'warehouse_id': transfer.warehouse_to_id.id,
            'nomenclature_id': self.nomenclature_id.id,
            'batch_name': self.lot_batch,
            'company_id': transfer.company_id.id,
            'qty_on_hand': self.qty,
            'uom_id': self.selected_uom_id.id,
            'source_document_type': 'transfer',
            'source_document_number': transfer.number,
            'operation_type': 'add',
            'last_movement_date': transfer.posting_datetime,
        }
        
        self.env['stock.warehouse.inventory'].create([vals])


class StockTransfer(models.Model):
    _inherit = 'stock.transfer'
    
    def action_done(self):
        """Оновлена версія проведення документа"""
        self.ensure_one()
        
        if self.state != 'confirmed':
            raise UserError("Можна провести тільки підтверджений документ")
        
        if not self.line_ids:
            raise UserError("Додайте позиції для переміщення")
        
        # Перевіряємо доступність всіх товарів
        for line in self.line_ids:
            line._validate_stock_availability()
        
        # Виконуємо переміщення
        self.posting_datetime = fields.Datetime.now()
        
        for line in self.line_ids:
            line._process_transfer_movement()
        
        # Змінюємо статус
        self.state = 'done'
        
        # Додаємо повідомлення в чат
        self.message_post(
            body=f"Документ переміщення №{self.number} успішно проведено",
            subject="Переміщення проведено"
        )
        
        return True


# Розширення для stock_balance модуля
class StockBalance(models.Model):
    _inherit = 'stock.balance'
    
    def action_show_warehouse_inventory(self):
        """Показує поточні залишки з централізованої таблиці"""
        # Формуємо домен на основі параметрів звіту
        domain = [('active', '=', True)]
        
        if self.company_ids:
            domain.append(('company_id', 'in', self.company_ids.ids))
        if self.warehouse_ids:
            domain.append(('warehouse_id', 'in', self.warehouse_ids.ids))
        if self.category_ids:
            domain.append(('nomenclature_id.categ_id', 'in', self.category_ids.ids))
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Поточні залишки товарів',
            'res_model': 'stock.warehouse.inventory',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'search_default_available': 1,
                'search_default_group_warehouse': 1,
            }
        }