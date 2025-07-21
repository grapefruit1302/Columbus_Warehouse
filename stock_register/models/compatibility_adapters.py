from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class StockBatchCompatibilityAdapter(models.Model):
    """
    Адаптер для backward compatibility з старою моделлю stock.batch
    Забезпечує роботу існуючих викликів через регістр накопичення
    """
    _name = 'stock.batch'
    _description = 'Адаптер партій для backward compatibility'
    _rec_name = 'batch_number'

    # Основні поля для сумісності
    batch_number = fields.Char('Номер партії', required=True, index=True)
    nomenclature_id = fields.Many2one('product.nomenclature', 'Номенклатура', required=True)
    current_qty = fields.Float('Поточна кількість', compute='_compute_current_qty')
    available_qty = fields.Float('Доступна кількість', compute='_compute_current_qty')
    location_id = fields.Many2one('stock.location', 'Локація')
    warehouse_id = fields.Many2one('stock.warehouse', 'Склад')
    company_id = fields.Many2one('res.company', 'Компанія', default=lambda self: self.env.company)
    date_created = fields.Datetime('Дата створення', compute='_compute_date_created')
    state = fields.Selection([
        ('active', 'Активна'),
        ('depleted', 'Вичерпана'),
        ('expired', 'Прострочена'),
        ('blocked', 'Заблокована'),
    ], 'Статус', compute='_compute_state')

    def _compute_current_qty(self):
        """Обчислює поточну кількість з регістра накопичення"""
        register_model = self.env['stock.balance.register']
        
        for batch in self:
            dimensions = {
                'nomenclature_id': batch.nomenclature_id.id,
                'batch_number': batch.batch_number,
                'company_id': batch.company_id.id,
            }
            
            if batch.warehouse_id:
                dimensions['warehouse_id'] = batch.warehouse_id.id
            if batch.location_id:
                dimensions['location_id'] = batch.location_id.id
                
            balance = register_model.get_balance(dimensions=dimensions)
            batch.current_qty = balance
            batch.available_qty = balance  # Поки без резервування

    def _compute_date_created(self):
        """Отримує дату створення партії з першого запису в регістрі"""
        for batch in self:
            first_record = self.env['stock.balance.register'].search([
                ('batch_number', '=', batch.batch_number),
                ('nomenclature_id', '=', batch.nomenclature_id.id),
                ('quantity', '>', 0),
            ], order='period asc', limit=1)
            
            batch.date_created = first_record.period if first_record else fields.Datetime.now()

    def _compute_state(self):
        """Обчислює статус партії"""
        for batch in self:
            if batch.current_qty <= 0:
                batch.state = 'depleted'
            else:
                batch.state = 'active'

    @api.model
    def get_fifo_batches(self, nomenclature_id, location_id, qty_needed, company_id=None):
        """
        Backward compatibility метод для отримання партій за FIFO
        Перенаправляє на регістр накопичення
        """
        register_model = self.env['stock.balance.register']
        
        if company_id is None:
            company_id = self.env.company.id
        
        location = self.env['stock.location'].browse(location_id)
        warehouse = location.warehouse_id
        
        location_dimensions = {}
        if warehouse:
            location_dimensions['warehouse_id'] = warehouse.id
            
        try:
            fifo_batches = register_model.fifo_consumption(
                nomenclature_id=nomenclature_id,
                quantity=qty_needed,
                location_dimensions=location_dimensions,
                company_id=company_id
            )
            
            # Адаптуємо формат відповіді для сумісності
            result_batches = []
            remaining_qty = 0
            
            for batch_info in fifo_batches:
                # Створюємо тимчасовий об'єкт партії для сумісності
                batch_record = self.new({
                    'batch_number': batch_info['batch_number'],
                    'nomenclature_id': nomenclature_id,
                    'warehouse_id': warehouse.id if warehouse else False,
                    'location_id': location_id,
                    'company_id': company_id,
                })
                
                result_batches.append({
                    'batch': batch_record,
                    'qty': batch_info['quantity'],
                })
            
            return result_batches, remaining_qty
            
        except ValidationError as e:
            # Якщо недостатньо залишку, повертаємо що є
            return [], qty_needed

    @api.model  
    def create_batch_from_receipt(self, nomenclature_id, receipt_number, qty, uom_id, 
                                  location_id, company_id, date_created=None, serial_numbers=None):
        """
        Backward compatibility метод створення партії
        Перенаправляє на регістр накопичення  
        """
        register_model = self.env['stock.balance.register']
        
        location = self.env['stock.location'].browse(location_id)
        warehouse = location.warehouse_id
        
        location_dims = {}
        if warehouse:
            location_dims['warehouse_id'] = warehouse.id
            location_dims['location_id'] = location_id

        receipt_doc = {
            'document_reference': receipt_number,
            'recorder_type': 'legacy.batch.creation',
            'recorder_id': 0,  # Для legacy записів
            'period': date_created or fields.Datetime.now(),
        }
        
        # Створюємо партію через регістр
        batch_number = register_model.create_batch_from_receipt(
            nomenclature_id=nomenclature_id,
            quantity=qty,
            receipt_doc=receipt_doc,
            location_dims=location_dims,
            serial_numbers=serial_numbers.split(',') if serial_numbers else None
        )
        
        # Повертаємо адаптер партії для сумісності
        batch_adapter = self.new({
            'batch_number': batch_number,
            'nomenclature_id': nomenclature_id,
            'warehouse_id': warehouse.id if warehouse else False,
            'location_id': location_id,
            'company_id': company_id,
        })
        
        return batch_adapter

    def consume_qty(self, qty, operation_type='consumption', document_reference='', notes=''):
        """
        Backward compatibility метод списання з партії
        Перенаправляє на регістр накопичення
        """
        self.ensure_one()
        register_model = self.env['stock.balance.register']
        
        # Створюємо запис списання в регістрі
        dimensions = {
            'nomenclature_id': self.nomenclature_id.id,
            'batch_number': self.batch_number,
            'company_id': self.company_id.id,
        }
        
        if self.warehouse_id:
            dimensions['warehouse_id'] = self.warehouse_id.id
        if self.location_id:
            dimensions['location_id'] = self.location_id.id
            
        resources = {
            'quantity': -qty,  # Від'ємна для списання
            'uom_id': self.nomenclature_id.base_uom_id.id,
        }
        
        attributes = {
            'operation_type': operation_type,
            'document_reference': document_reference,
            'recorder_type': 'legacy.consumption',
            'recorder_id': 0,
            'period': fields.Datetime.now(),
            'notes': notes,
        }
        
        register_model.write_record(dimensions, resources, attributes)
        
        return True


class StockBalanceCompatibilityAdapter(models.Model):
    """
    Адаптер для backward compatibility з старою моделлю stock.balance
    """
    _name = 'stock.balance'
    _description = 'Адаптер залишків для backward compatibility'
    _rec_name = 'display_name'

    # Поля для сумісності
    nomenclature_id = fields.Many2one('product.nomenclature', 'Номенклатура', required=True)
    warehouse_id = fields.Many2one('stock.warehouse', 'Склад')
    location_id = fields.Many2one('stock.location', 'Локація')
    employee_id = fields.Many2one('hr.employee', 'Працівник')
    batch_id = fields.Many2one('stock.batch', 'Партія')  # Ссилка на адаптер партії
    qty_on_hand = fields.Float('Фізична кількість', compute='_compute_quantities')
    qty_available = fields.Float('Доступна кількість', compute='_compute_quantities')
    company_id = fields.Many2one('res.company', 'Компанія', default=lambda self: self.env.company)
    location_type = fields.Selection([
        ('warehouse', 'Склад'),
        ('employee', 'Працівник'),
    ], 'Тип локації', default='warehouse')
    display_name = fields.Char('Назва', compute='_compute_display_name')

    def _compute_quantities(self):
        """Обчислює кількості з регістра накопичення"""
        register_model = self.env['stock.balance.register']
        
        for balance in self:
            dimensions = {
                'nomenclature_id': balance.nomenclature_id.id,
                'company_id': balance.company_id.id,
            }
            
            if balance.location_type == 'warehouse' and balance.warehouse_id:
                dimensions['warehouse_id'] = balance.warehouse_id.id
                if balance.location_id:
                    dimensions['location_id'] = balance.location_id.id
            elif balance.location_type == 'employee' and balance.employee_id:
                dimensions['employee_id'] = balance.employee_id.id
                
            if balance.batch_id:
                dimensions['batch_number'] = balance.batch_id.batch_number
                
            qty = register_model.get_balance(dimensions=dimensions)
            balance.qty_on_hand = qty
            balance.qty_available = qty

    def _compute_display_name(self):
        """Обчислює відображувану назву"""
        for balance in self:
            parts = []
            
            if balance.nomenclature_id:
                parts.append(balance.nomenclature_id.name)
            
            if balance.location_type == 'warehouse' and balance.warehouse_id:
                parts.append(f"Склад: {balance.warehouse_id.name}")
            elif balance.location_type == 'employee' and balance.employee_id:
                parts.append(f"Працівник: {balance.employee_id.name}")
            
            if balance.batch_id:
                parts.append(f"Партія: {balance.batch_id.batch_number}")
            
            balance.display_name = " | ".join(parts)

    @api.model
    def get_balance(self, nomenclature_id, location_type='warehouse', warehouse_id=None,
                   employee_id=None, location_id=None, batch_id=None, company_id=None):
        """Backward compatibility метод отримання залишку"""
        register_model = self.env['stock.balance.register']
        
        dimensions = {
            'nomenclature_id': nomenclature_id,
            'company_id': company_id or self.env.company.id,
        }
        
        if location_type == 'warehouse' and warehouse_id:
            dimensions['warehouse_id'] = warehouse_id
            if location_id:
                dimensions['location_id'] = location_id
        elif location_type == 'employee' and employee_id:
            dimensions['employee_id'] = employee_id
            
        if batch_id:
            batch = self.env['stock.batch'].browse(batch_id)
            if batch.exists():
                dimensions['batch_number'] = batch.batch_number
                
        return register_model.get_balance(dimensions=dimensions)

    @api.model
    def update_balance(self, nomenclature_id, qty_change, location_type='warehouse',
                      warehouse_id=None, employee_id=None, location_id=None,
                      batch_id=None, uom_id=None, company_id=None, serial_numbers=None):
        """Backward compatibility метод оновлення залишку"""
        register_model = self.env['stock.balance.register']
        
        dimensions = {
            'nomenclature_id': nomenclature_id,
            'company_id': company_id or self.env.company.id,
        }
        
        if location_type == 'warehouse' and warehouse_id:
            dimensions['warehouse_id'] = warehouse_id
            if location_id:
                dimensions['location_id'] = location_id
        elif location_type == 'employee' and employee_id:
            dimensions['employee_id'] = employee_id
            
        if batch_id:
            batch = self.env['stock.batch'].browse(batch_id)
            if batch.exists():
                dimensions['batch_number'] = batch.batch_number
                
        resources = {
            'quantity': qty_change,
            'uom_id': uom_id or self.env['product.nomenclature'].browse(nomenclature_id).base_uom_id.id,
        }
        
        attributes = {
            'operation_type': 'adjustment' if qty_change != 0 else 'inventory',
            'document_reference': 'Legacy Balance Update',
            'recorder_type': 'legacy.balance.update', 
            'recorder_id': 0,
            'period': fields.Datetime.now(),
            'notes': 'Backward compatibility update',
        }
        
        # Обробляємо серійні номери
        if serial_numbers and isinstance(serial_numbers, str):
            # Якщо товар з серійним обліком, створюємо окремі записи
            nomenclature = self.env['product.nomenclature'].browse(nomenclature_id)
            if nomenclature.tracking_serial:
                serial_list = [s.strip() for s in serial_numbers.replace(',', '\n').split('\n') if s.strip()]
                for serial in serial_list:
                    serial_dimensions = dimensions.copy()
                    serial_dimensions['serial_number'] = serial
                    
                    serial_resources = {
                        'quantity': 1.0 if qty_change > 0 else -1.0,
                        'uom_id': resources['uom_id'],
                    }
                    
                    register_model.write_record(serial_dimensions, serial_resources, attributes)
                return True
        
        # Для звичайних товарів або коли немає серійних номерів
        register_model.write_record(dimensions, resources, attributes)
        return True

    @api.model
    def get_fifo_balances(self, nomenclature_id, required_qty, location_type='warehouse',
                         warehouse_id=None, employee_id=None, company_id=None):
        """Backward compatibility FIFO метод"""
        register_model = self.env['stock.balance.register']
        
        location_dimensions = {}
        if location_type == 'warehouse' and warehouse_id:
            location_dimensions['warehouse_id'] = warehouse_id
        elif location_type == 'employee' and employee_id:
            location_dimensions['employee_id'] = employee_id
            
        try:
            fifo_batches = register_model.fifo_consumption(
                nomenclature_id=nomenclature_id,
                quantity=required_qty,
                location_dimensions=location_dimensions,
                company_id=company_id or self.env.company.id
            )
            
            # Адаптуємо для backward compatibility
            result_list = []
            remaining_qty = 0
            
            for batch_info in fifo_batches:
                # Створюємо тимчасовий адаптер залишку
                balance_record = self.new({
                    'nomenclature_id': nomenclature_id,
                    'location_type': location_type,
                    'warehouse_id': warehouse_id,
                    'employee_id': employee_id,
                    'company_id': company_id or self.env.company.id,
                })
                
                result_list.append({
                    'balance': balance_record,
                    'qty': batch_info['quantity'],
                })
                
            return result_list, remaining_qty
            
        except ValidationError:
            return [], required_qty