from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class StockBalanceMovement(models.Model):
    _name = 'stock.balance.movement'
    _description = 'Рух залишків товарів'
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    # Основні поля
    nomenclature_id = fields.Many2one(
        'product.nomenclature', 
        'Номенклатура', 
        required=True,
        index=True
    )
    
    movement_type = fields.Selection([
        ('in', 'Надходження'),
        ('out', 'Списання'),
        ('transfer_in', 'Переміщення (надходження)'),
        ('transfer_out', 'Переміщення (списання)'),
        ('adjustment', 'Коригування'),
    ], 'Тип руху', required=True)
    
    operation_type = fields.Selection([
        ('receipt', 'Прихідна накладна'),
        ('disposal', 'Акт оприходування'),
        ('return_service', 'Повернення з сервісу'),
        ('transfer', 'Переміщення'),
        ('inventory', 'Інвентаризація'),
        ('writeoff', 'Списання'),
        ('consumption', 'Споживання'),
        ('adjustment', 'Коригування'),
    ], 'Тип операції', required=True)
    
    # Локації
    location_from_type = fields.Selection([
        ('warehouse', 'Склад'),
        ('employee', 'Працівник'),
        ('external', 'Зовнішня'),
    ], 'Тип локації (з)')
    
    location_to_type = fields.Selection([
        ('warehouse', 'Склад'),
        ('employee', 'Працівник'),
        ('external', 'Зовнішня'),
    ], 'Тип локації (в)')
    
    warehouse_from_id = fields.Many2one('stock.warehouse', 'Склад (з)')
    warehouse_to_id = fields.Many2one('stock.warehouse', 'Склад (в)')
    
    employee_from_id = fields.Many2one('hr.employee', 'Працівник (з)')
    employee_to_id = fields.Many2one('hr.employee', 'Працівник (в)')
    
    location_from_id = fields.Many2one('stock.location', 'Локація (з)')
    location_to_id = fields.Many2one('stock.location', 'Локація (в)')
    
    # Партія
    batch_id = fields.Many2one('stock.batch', 'Партія')
    
    # Кількості
    qty = fields.Float(
        'Кількість', 
        required=True,
        digits='Product Unit of Measure'
    )
    
    uom_id = fields.Many2one(
        'uom.uom', 
        'Одиниця виміру', 
        required=True
    )
    
    # Додаткові поля
    date = fields.Datetime(
        'Дата та час', 
        required=True,
        default=fields.Datetime.now,
        index=True
    )
    
    document_reference = fields.Char(
        'Документ', 
        help='Посилання на документ, що спричинив рух'
    )
    
    company_id = fields.Many2one(
        'res.company', 
        'Компанія', 
        required=True,
        default=lambda self: self.env.company
    )
    
    user_id = fields.Many2one(
        'res.users', 
        'Користувач', 
        required=True,
        default=lambda self: self.env.user
    )
    
    notes = fields.Text('Примітки')
    
    # Серійні номери
    serial_numbers = fields.Text('Серійні номери')
    
    # Розрахункове поле для відображення
    display_name = fields.Char(
        'Назва',
        compute='_compute_display_name',
        store=True
    )

    @api.depends('movement_type', 'operation_type', 'nomenclature_id', 'qty', 'date')
    def _compute_display_name(self):
        for movement in self:
            operation_label = dict(movement._fields['operation_type'].selection).get(
                movement.operation_type, movement.operation_type
            )
            movement_label = dict(movement._fields['movement_type'].selection).get(
                movement.movement_type, movement.movement_type
            )
            
            name_parts = [
                operation_label,
                movement.nomenclature_id.name if movement.nomenclature_id else '',
                f"{movement.qty} {movement.uom_id.name if movement.uom_id else ''}",
                movement.date.strftime('%d.%m.%Y %H:%M') if movement.date else ''
            ]
            
            movement.display_name = " | ".join(filter(None, name_parts))

    @api.model
    def create_movement(self, nomenclature_id, qty, movement_type, operation_type,
                       location_from_type=None, location_to_type=None,
                       warehouse_from_id=None, warehouse_to_id=None,
                       employee_from_id=None, employee_to_id=None,
                       location_from_id=None, location_to_id=None,
                       batch_id=None, uom_id=None, document_reference=None,
                       notes=None, serial_numbers=None, company_id=None, date=None):
        """Створює рух залишків та оновлює баланси"""
        
        if company_id is None:
            company_id = self.env.company.id
        
        if uom_id is None:
            nomenclature = self.env['product.nomenclature'].browse(nomenclature_id)
            uom_id = nomenclature.base_uom_id.id
        
        if date is None:
            date = fields.Datetime.now()
        
        # Створюємо запис руху
        movement_vals = {
            'nomenclature_id': nomenclature_id,
            'movement_type': movement_type,
            'operation_type': operation_type,
            'qty': qty,
            'uom_id': uom_id,
            'date': date,
            'document_reference': document_reference,
            'notes': notes,
            'serial_numbers': serial_numbers,
            'company_id': company_id,
            'batch_id': batch_id,
            'location_from_type': location_from_type,
            'location_to_type': location_to_type,
            'warehouse_from_id': warehouse_from_id,
            'warehouse_to_id': warehouse_to_id,
            'employee_from_id': employee_from_id,
            'employee_to_id': employee_to_id,
            'location_from_id': location_from_id,
            'location_to_id': location_to_id,
        }
        
        movement = self.create(movement_vals)
        
        # Оновлюємо баланси
        self._update_balances_from_movement(movement)
        
        return movement

    def _update_balances_from_movement(self, movement):
        """Оновлює баланси на основі руху"""
        Balance = self.env['stock.balance']
        
        # Списання з локації відправлення
        if movement.location_from_type in ['warehouse', 'employee']:
            if movement.location_from_type == 'warehouse':
                Balance.update_balance(
                    nomenclature_id=movement.nomenclature_id.id,
                    qty_change=-movement.qty,
                    location_type='warehouse',
                    warehouse_id=movement.warehouse_from_id.id,
                    location_id=movement.location_from_id.id if movement.location_from_id else None,
                    batch_id=movement.batch_id.id if movement.batch_id else None,
                    uom_id=movement.uom_id.id,
                    company_id=movement.company_id.id,
                )
            else:  # employee
                Balance.update_balance(
                    nomenclature_id=movement.nomenclature_id.id,
                    qty_change=-movement.qty,
                    location_type='employee',
                    employee_id=movement.employee_from_id.id,
                    batch_id=movement.batch_id.id if movement.batch_id else None,
                    uom_id=movement.uom_id.id,
                    company_id=movement.company_id.id,
                )
        
        # Надходження в локацію призначення
        if movement.location_to_type in ['warehouse', 'employee']:
            if movement.location_to_type == 'warehouse':
                Balance.update_balance(
                    nomenclature_id=movement.nomenclature_id.id,
                    qty_change=movement.qty,
                    location_type='warehouse',
                    warehouse_id=movement.warehouse_to_id.id,
                    location_id=movement.location_to_id.id if movement.location_to_id else None,
                    batch_id=movement.batch_id.id if movement.batch_id else None,
                    uom_id=movement.uom_id.id,
                    company_id=movement.company_id.id,
                    serial_numbers=movement.serial_numbers,
                )
            else:  # employee
                Balance.update_balance(
                    nomenclature_id=movement.nomenclature_id.id,
                    qty_change=movement.qty,
                    location_type='employee',
                    employee_id=movement.employee_to_id.id,
                    batch_id=movement.batch_id.id if movement.batch_id else None,
                    uom_id=movement.uom_id.id,
                    company_id=movement.company_id.id,
                    serial_numbers=movement.serial_numbers,
                )