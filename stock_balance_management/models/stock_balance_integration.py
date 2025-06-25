# stock_balance_management/models/stock_balance_integration.py

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class StockTransferLine(models.Model):
    """Розширюємо позиції переміщень"""
    _inherit = 'stock.transfer.line'

    available_qty = fields.Float(
        'Доступна кількість',
        compute='_compute_available_qty',
        help='Доступна кількість в локації відправника'
    )

    @api.depends('nomenclature_id', 'transfer_id.transfer_type', 
                 'transfer_id.warehouse_from_id', 'transfer_id.employee_from_id')
    def _compute_available_qty(self):
        for line in self:
            if not line.nomenclature_id or not line.transfer_id:
                line.available_qty = 0.0
                continue
            
            Balance = self.env['stock.balance']
            transfer = line.transfer_id
            
            if transfer.transfer_type in ['warehouse', 'warehouse_employee']:
                if transfer.warehouse_from_id:
                    line.available_qty = Balance.get_available_qty(
                        nomenclature_id=line.nomenclature_id.id,
                        location_type='warehouse',
                        warehouse_id=transfer.warehouse_from_id.id,
                        company_id=transfer.company_id.id
                    )
                else:
                    line.available_qty = 0.0
            elif transfer.transfer_type in ['employee', 'employee_warehouse']:
                if transfer.employee_from_id:
                    line.available_qty = Balance.get_available_qty(
                        nomenclature_id=line.nomenclature_id.id,
                        location_type='employee',
                        employee_id=transfer.employee_from_id.id,
                        company_id=transfer.company_id.id
                    )
                else:
                    line.available_qty = 0.0
            else:
                line.available_qty = 0.0

    @api.constrains('qty', 'nomenclature_id')
    def _check_qty_availability(self):
        """Перевіряє доступність товару при зміні кількості"""
        for line in self:
            if (line.qty > 0 and line.available_qty < line.qty and 
                line.transfer_id.state != 'draft'):
                raise ValidationError(
                    _('Недостатньо товару "%s". Доступно: %s, потрібно: %s') % (
                        line.nomenclature_id.name,
                        line.available_qty,
                        line.qty
                    )
                )


class StockTransfer(models.Model):
    """Розширюємо модель переміщень для роботи з залишками"""
    _inherit = 'stock.transfer'

    def action_done(self):
        """Перевіряємо доступність товарів перед проведенням"""
        # Спочатку перевіряємо доступність всіх товарів
        for line in self.line_ids:
            self._check_line_availability(line)
        
        # Якщо все ОК, проводимо переміщення
        result = super().action_done()
        
        # Створюємо рухи залишків
        for line in self.line_ids:
            try:
                self._create_balance_movements_for_line(line)
            except Exception as e:
                _logger.error(f"Помилка створення руху залишків для {line.nomenclature_id.name}: {e}")
                self.message_post(
                    body=_('Помилка оновлення залишків для %s: %s') % (line.nomenclature_id.name, str(e)),
                    message_type='notification'
                )
        
        return result

    def _check_line_availability(self, line):
        """Перевіряє доступність товару для переміщення"""
        Balance = self.env['stock.balance']
        
        # Визначаємо локацію відправника
        if self.transfer_type == 'warehouse':
            available_qty = Balance.get_available_qty(
                nomenclature_id=line.nomenclature_id.id,
                location_type='warehouse',
                warehouse_id=self.warehouse_from_id.id,
                company_id=self.company_id.id
            )
            location_name = self.warehouse_from_id.name
        elif self.transfer_type == 'employee':
            available_qty = Balance.get_available_qty(
                nomenclature_id=line.nomenclature_id.id,
                location_type='employee',
                employee_id=self.employee_from_id.id,
                company_id=self.company_id.id
            )
            location_name = self.employee_from_id.name
        elif self.transfer_type == 'employee_warehouse':
            available_qty = Balance.get_available_qty(
                nomenclature_id=line.nomenclature_id.id,
                location_type='employee',
                employee_id=self.employee_from_id.id,
                company_id=self.company_id.id
            )
            location_name = self.employee_from_id.name
        elif self.transfer_type == 'warehouse_employee':
            available_qty = Balance.get_available_qty(
                nomenclature_id=line.nomenclature_id.id,
                location_type='warehouse',
                warehouse_id=self.warehouse_from_id.id,
                company_id=self.company_id.id
            )
            location_name = self.warehouse_from_id.name
        else:
            raise UserError(_('Невідомий тип переміщення: %s') % self.transfer_type)
        
        if available_qty < line.qty:
            raise UserError(
                _('Недостатньо товару "%s" в локації "%s".\n'
                  'Доступно: %s, потрібно: %s') % (
                    line.nomenclature_id.name,
                    location_name,
                    available_qty,
                    line.qty
                )
            )

    def _create_balance_movements_for_line(self, line):
        """Створює рухи залишків для позиції переміщення"""
        if line.qty <= 0:
            return
        
        Movement = self.env['stock.balance.movement']
        
        # Визначаємо параметри руху залежно від типу переміщення
        if self.transfer_type == 'warehouse':
            # Між складами
            location_from_id = self.warehouse_from_id.lot_stock_id.id
            location_to_id = self.warehouse_to_id.lot_stock_id.id
            
            # Використовуємо FIFO для вибору партій
            fifo_balances, remaining_qty = self.env['stock.balance'].get_fifo_balances(
                nomenclature_id=line.nomenclature_id.id,
                required_qty=line.qty,
                location_type='warehouse',
                warehouse_id=self.warehouse_from_id.id,
                company_id=self.company_id.id
            )
            
            for fifo_item in fifo_balances:
                batch_id = fifo_item['balance'].batch_id.id if fifo_item['balance'].batch_id else None
                
                Movement.create_movement(
                    nomenclature_id=line.nomenclature_id.id,
                    qty=fifo_item['qty'],
                    movement_type='transfer_out',
                    operation_type='transfer',
                    location_from_type='warehouse',
                    location_to_type='warehouse',
                    warehouse_from_id=self.warehouse_from_id.id,
                    warehouse_to_id=self.warehouse_to_id.id,
                    location_from_id=location_from_id,
                    location_to_id=location_to_id,
                    batch_id=batch_id,
                    uom_id=line.selected_uom_id.id,
                    document_reference=self.number,
                    notes=f'Переміщення {self.number}: {self.warehouse_from_id.name} → {self.warehouse_to_id.name}',
                    company_id=self.company_id.id,
                    date=self.posting_datetime,
                )
        
        elif self.transfer_type == 'employee':
            # Між працівниками
            fifo_balances, remaining_qty = self.env['stock.balance'].get_fifo_balances(
                nomenclature_id=line.nomenclature_id.id,
                required_qty=line.qty,
                location_type='employee',
                employee_id=self.employee_from_id.id,
                company_id=self.company_id.id
            )
            
            for fifo_item in fifo_balances:
                batch_id = fifo_item['balance'].batch_id.id if fifo_item['balance'].batch_id else None
                
                Movement.create_movement(
                    nomenclature_id=line.nomenclature_id.id,
                    qty=fifo_item['qty'],
                    movement_type='transfer_out',
                    operation_type='transfer',
                    location_from_type='employee',
                    location_to_type='employee',
                    employee_from_id=self.employee_from_id.id,
                    employee_to_id=self.employee_to_id.id,
                    batch_id=batch_id,
                    uom_id=line.selected_uom_id.id,
                    document_reference=self.number,
                    notes=f'Переміщення {self.number}: {self.employee_from_id.name} → {self.employee_to_id.name}',
                    company_id=self.company_id.id,
                    date=self.posting_datetime,
                )
        
        elif self.transfer_type == 'warehouse_employee':
            # Зі складу працівнику
            location_from_id = self.warehouse_from_id.lot_stock_id.id
            
            fifo_balances, remaining_qty = self.env['stock.balance'].get_fifo_balances(
                nomenclature_id=line.nomenclature_id.id,
                required_qty=line.qty,
                location_type='warehouse',
                warehouse_id=self.warehouse_from_id.id,
                company_id=self.company_id.id
            )
            
            for fifo_item in fifo_balances:
                batch_id = fifo_item['balance'].batch_id.id if fifo_item['balance'].batch_id else None
                
                Movement.create_movement(
                    nomenclature_id=line.nomenclature_id.id,
                    qty=fifo_item['qty'],
                    movement_type='transfer_out',
                    operation_type='transfer',
                    location_from_type='warehouse',
                    location_to_type='employee',
                    warehouse_from_id=self.warehouse_from_id.id,
                    employee_to_id=self.employee_to_id.id,
                    location_from_id=location_from_id,
                    batch_id=batch_id,
                    uom_id=line.selected_uom_id.id,
                    document_reference=self.number,
                    notes=f'Переміщення {self.number}: {self.warehouse_from_id.name} → {self.employee_to_id.name}',
                    company_id=self.company_id.id,
                    date=self.posting_datetime,
                )
        
        elif self.transfer_type == 'employee_warehouse':
            # Від працівника на склад
            location_to_id = self.warehouse_to_id.lot_stock_id.id
            
            fifo_balances, remaining_qty = self.env['stock.balance'].get_fifo_balances(
                nomenclature_id=line.nomenclature_id.id,
                required_qty=line.qty,
                location_type='employee',
                employee_id=self.employee_from_id.id,
                company_id=self.company_id.id
            )
            
            for fifo_item in fifo_balances:
                batch_id = fifo_item['balance'].batch_id.id if fifo_item['balance'].batch_id else None
                
                Movement.create_movement(
                    nomenclature_id=line.nomenclature_id.id,
                    qty=fifo_item['qty'],
                    movement_type='transfer_out',
                    operation_type='transfer',
                    location_from_type='employee',
                    location_to_type='warehouse',
                    employee_from_id=self.employee_from_id.id,
                    warehouse_to_id=self.warehouse_to_id.id,
                    location_to_id=location_to_id,
                    batch_id=batch_id,
                    uom_id=line.selected_uom_id.id,
                    document_reference=self.number,
                    notes=f'Переміщення {self.number}: {self.employee_from_id.name} → {self.warehouse_to_id.name}',
                    company_id=self.company_id.id,
                    date=self.posting_datetime,
                )