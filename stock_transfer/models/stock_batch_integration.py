# Додай цей файл: stock_transfer/models/stock_batch_integration.py

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class StockTransfer(models.Model):
    """Розширення для інтеграції з партіями"""
    _inherit = 'stock.transfer'

    def action_done(self):
        """Додаємо створення рухів партій"""
        # Спочатку стандартна логіка
        result = super().action_done()
        
        # Потім створюємо рухи партій якщо модуль встановлений
        if 'stock.batch.movement' in self.env:
            for line in self.line_ids:
                self._create_batch_movements_for_line(line)
        
        return result

    def _create_batch_movements_for_line(self, line):
        """Створює рухи партій для позиції переміщення"""
        if line.qty <= 0:
            return
        
        BatchMovement = self.env['stock.batch.movement']
        company_ids = self._get_child_companies(self.company_id)
        
        # Знаходимо партії які беруть участь в переміщенні (FIFO)
        if self.transfer_type in ['warehouse', 'warehouse_employee']:
            source_location_type = 'warehouse'
            source_id = self.warehouse_from_id.id
        elif self.transfer_type in ['employee', 'employee_warehouse']:
            source_location_type = 'employee'
            source_id = self.employee_from_id.id
        else:
            return
        
        # Шукаємо залишки з партіями за FIFO
        domain = [
            ('nomenclature_id', '=', line.nomenclature_id.id),
            ('location_type', '=', source_location_type),
            ('company_id', 'in', company_ids),
            ('qty_available', '>', 0),
            ('batch_id', '!=', False)  # Тільки з партіями
        ]
        
        if source_location_type == 'warehouse':
            domain.append(('warehouse_id', '=', source_id))
        else:
            domain.append(('employee_id', '=', source_id))
        
        balances = self.env['stock.balance'].search(domain, order='batch_id ASC, id ASC')
        
        remaining_qty = line.qty
        for balance in balances:
            if remaining_qty <= 0:
                break
            
            if not balance.batch_id:
                continue
                
            take_qty = min(balance.qty_available, remaining_qty)
            
            # Створюємо рух партії (списання)
            BatchMovement.create({
                'batch_id': balance.batch_id.id,
                'movement_type': 'transfer_out',
                'operation_type': 'transfer',
                'qty': take_qty,
                'uom_id': line.selected_uom_id.id,
                'location_from_id': self._get_location_from_balance(balance),
                'location_to_id': self._get_location_to_transfer(),
                'document_reference': self.number,
                'notes': self._get_transfer_notes(),
                'date': self.posting_datetime or fields.Datetime.now(),
                'user_id': self.env.user.id,
                'company_id': balance.company_id.id,
            })
            
            # Якщо є пункт призначення - створюємо рух надходження
            if self._should_create_destination_movement():
                BatchMovement.create({
                    'batch_id': balance.batch_id.id,
                    'movement_type': 'transfer_in',
                    'operation_type': 'transfer',
                    'qty': take_qty,
                    'uom_id': line.selected_uom_id.id,
                    'location_from_id': self._get_location_from_balance(balance),
                    'location_to_id': self._get_location_to_transfer(),
                    'document_reference': self.number,
                    'notes': self._get_transfer_notes(),
                    'date': self.posting_datetime or fields.Datetime.now(),
                    'user_id': self.env.user.id,
                    'company_id': self.company_id.id,  # Компанія одержувача
                })
            
            remaining_qty -= take_qty

    def _get_location_from_balance(self, balance):
        """Повертає ID локації з залишку"""
        if balance.location_type == 'warehouse':
            return balance.warehouse_id.lot_stock_id.id if balance.warehouse_id else None
        else:
            return None  # Для працівників може не бути stock.location

    def _get_location_to_transfer(self):
        """Повертає ID локації призначення"""
        if self.transfer_type in ['warehouse', 'employee_warehouse']:
            return self.warehouse_to_id.lot_stock_id.id if self.warehouse_to_id else None
        elif self.transfer_type in ['warehouse_employee', 'employee']:
            return None  # Для працівників може не бути stock.location
        return None

    def _should_create_destination_movement(self):
        """Чи потрібно створювати рух надходження в пункт призначення"""
        # Створюємо рух надходження тільки для переміщень між складами
        return self.transfer_type == 'warehouse'

    def _get_transfer_notes(self):
        """Повертає примітки для руху партії"""
        if self.transfer_type == 'warehouse':
            return f'Переміщення {self.number}: {self.warehouse_from_id.name} → {self.warehouse_to_id.name}'
        elif self.transfer_type == 'warehouse_employee':
            return f'Видача {self.number}: {self.warehouse_from_id.name} → {self.employee_to_id.name}'
        elif self.transfer_type == 'employee_warehouse':
            return f'Повернення {self.number}: {self.employee_from_id.name} → {self.warehouse_to_id.name}'
        elif self.transfer_type == 'employee':
            return f'Переміщення {self.number}: {self.employee_from_id.name} → {self.employee_to_id.name}'
        return f'Переміщення {self.number}'

    def action_view_batch_movements(self):
        """Відкриває рухи партій пов'язані з цим переміщенням"""
        self.ensure_one()
        
        if 'stock.batch.movement' not in self.env:
            raise UserError('Модуль партійного обліку не встановлений!')
        
        movements = self.env['stock.batch.movement'].search([
            ('document_reference', '=', self.number)
        ])
        
        return {
            'name': f'Рухи партій для {self.number}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.batch.movement',
            'view_mode': 'list,form',
            'domain': [('id', 'in', movements.ids)],
            'context': {
                'search_default_document_reference': self.number,
            }
        }