from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class StockBalance(models.Model):
    _name = 'stock.balance'
    _description = 'Залишки товарів'
    _order = 'nomenclature_id, location_id, batch_id'
    _rec_name = 'display_name'

    # Основні поля
    nomenclature_id = fields.Many2one(
        'product.nomenclature', 
        'Номенклатура', 
        required=True,
        index=True
    )
    
    # Локація може бути складом або працівником
    location_type = fields.Selection([
        ('warehouse', 'Склад'),
        ('employee', 'Працівник'),
    ], 'Тип локації', required=True, default='warehouse')
    
    warehouse_id = fields.Many2one(
        'stock.warehouse', 
        'Склад',
        index=True
    )
    
    location_id = fields.Many2one(
        'stock.location', 
        'Локація складу'
    )
    
    employee_id = fields.Many2one(
        'hr.employee', 
        'Працівник',
        index=True
    )
    
    # Партія (якщо товар партійний)
    batch_id = fields.Many2one(
        'stock.batch', 
        'Партія',
        index=True
    )
    
    # Кількості
    qty_on_hand = fields.Float(
        'Фізична кількість', 
        default=0.0,
        digits='Product Unit of Measure',
        help='Фактична кількість товару'
    )
    
    qty_available = fields.Float(
        'Доступна кількість',
        compute='_compute_available_qty',
        store=True,
        digits='Product Unit of Measure',
        help='Кількість доступна для операцій (залежить від серійних номерів)'
    )
    
    # НОВІ ПОЛЯ для серійних номерів
    has_serial_tracking = fields.Boolean(
        'Має серійний облік',
        related='nomenclature_id.tracking_serial',
        readonly=True,
        help='Чи має товар облік по серійних номерах'
    )
    
    serial_numbers_count = fields.Integer(
        'Кількість введених S/N',
        compute='_compute_serial_info',
        store=True,
        help='Кількість введених серійних номерів'
    )
    
    missing_serial_count = fields.Float(
        'Без серійних номерів',
        compute='_compute_available_qty',
        store=True,
        digits='Product Unit of Measure',
        help='Кількість товару без введених серійних номерів'
    )
    
    # Додаткові поля
    uom_id = fields.Many2one(
        'uom.uom', 
        'Одиниця виміру', 
        required=True
    )
    
    company_id = fields.Many2one(
        'res.company', 
        'Компанія', 
        required=True,
        default=lambda self: self.env.company
    )
    
    last_update = fields.Datetime(
        'Останнє оновлення', 
        default=fields.Datetime.now,
        readonly=True
    )
    
    # Серійні номери (для товарів з серійним обліком)
    serial_numbers = fields.Text(
        'Серійні номери',
        help='Серійні номери товарів (для товарів з S/N обліком)'
    )
    
    # Розрахункове поле для відображення
    display_name = fields.Char(
        'Назва',
        compute='_compute_display_name',
        store=True
    )

    _sql_constraints = [
        ('unique_balance_record', 
         'unique(nomenclature_id, location_type, warehouse_id, location_id, employee_id, batch_id, company_id)', 
         'Запис залишків має бути унікальним для комбінації номенклатури, локації, партії та компанії!'),
        ('check_location_consistency', 
         'CHECK((location_type = \'warehouse\' AND warehouse_id IS NOT NULL AND employee_id IS NULL) OR '
               '(location_type = \'employee\' AND employee_id IS NOT NULL AND warehouse_id IS NULL))', 
         'Повинна бути вказана або локація складу, або працівник, але не обидва!'),
    ]

    @api.depends('serial_numbers')
    def _compute_serial_info(self):
        """Розраховує кількість введених серійних номерів"""
        for balance in self:
            if balance.serial_numbers:
                serials = balance.get_serial_numbers_list()
                balance.serial_numbers_count = len(serials)
            else:
                balance.serial_numbers_count = 0

    @api.depends('qty_on_hand', 'serial_numbers_count', 'has_serial_tracking')
    def _compute_available_qty(self):
        """НОВА ЛОГІКА: доступна кількість залежить від серійних номерів"""
        for balance in self:
            if balance.has_serial_tracking:
                # Для товарів з серійним обліком: доступна кількість = кількість введених серійних номерів
                balance.qty_available = balance.serial_numbers_count
                balance.missing_serial_count = balance.qty_on_hand - balance.serial_numbers_count
            else:
                # Для товарів без серійного обліку: доступна кількість = фізична кількість
                balance.qty_available = balance.qty_on_hand
                balance.missing_serial_count = 0.0

    def get_serial_numbers_list(self):
        """Повертає список серійних номерів"""
        self.ensure_one()
        if not self.serial_numbers:
            return []
        
        serials = []
        for line in self.serial_numbers.split('\n'):
            for serial in line.split(','):
                serial = serial.strip()
                if serial:
                    serials.append(serial)
        return serials

    def get_serial_numbers_detailed(self):
        """Повертає детальну інформацію про серійні номери"""
        self.ensure_one()
        serials = self.get_serial_numbers_list()
        
        detailed_info = []
        for i, serial in enumerate(serials, 1):
            # Тут можна додати додаткову інформацію про серійний номер
            # наприклад, дату надходження, документ, тощо
            detailed_info.append({
                'number': i,
                'serial_number': serial,
                'status': 'available',  # можна розширити статуси
                'batch_number': self.batch_id.batch_number if self.batch_id else '',
                'location': self._get_location_name(),
            })
        
        return detailed_info

    def _get_location_name(self):
        """Повертає назву локації"""
        if self.location_type == 'warehouse':
            return self.warehouse_id.name if self.warehouse_id else ''
        else:
            return self.employee_id.name if self.employee_id else ''

    def action_view_serial_numbers(self):
        """Відкриває розширений візард для перегляду серійних номерів"""
        self.ensure_one()
        
        if not self.serial_numbers:
            raise UserError('У цього залишку немає серійних номерів!')
        
        return {
            'name': f'Серійні номери - {self.nomenclature_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.balance.serial.detailed.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_balance_id': self.id},
        }

    def action_manage_serial_numbers(self):
        """Відкриває візард для управління серійними номерами"""
        self.ensure_one()
        
        return {
            'name': f'Управління серійними номерами - {self.nomenclature_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.balance.serial.management.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_balance_id': self.id},
        }

    @api.depends('nomenclature_id', 'location_type', 'warehouse_id', 'employee_id', 'batch_id')
    def _compute_display_name(self):
        for balance in self:
            name_parts = [balance.nomenclature_id.name if balance.nomenclature_id else 'Товар']
            
            if balance.location_type == 'warehouse' and balance.warehouse_id:
                name_parts.append(f"Склад: {balance.warehouse_id.name}")
            elif balance.location_type == 'employee' and balance.employee_id:
                name_parts.append(f"Працівник: {balance.employee_id.name}")
            
            if balance.batch_id:
                name_parts.append(f"Партія: {balance.batch_id.batch_number}")
            
            balance.display_name = " | ".join(name_parts)

    # Решта методів залишається без змін...
    @api.model
    def get_balance(self, nomenclature_id, location_type='warehouse', warehouse_id=None, 
                   employee_id=None, location_id=None, batch_id=None, company_id=None):
        """Отримує поточний залишок для вказаних параметрів"""
        if company_id is None:
            company_id = self.env.company.id
        
        domain = [
            ('nomenclature_id', '=', nomenclature_id),
            ('location_type', '=', location_type),
            ('company_id', '=', company_id),
        ]
        
        if location_type == 'warehouse':
            domain.append(('warehouse_id', '=', warehouse_id))
            if location_id:
                domain.append(('location_id', '=', location_id))
        else:
            domain.append(('employee_id', '=', employee_id))
        
        if batch_id:
            domain.append(('batch_id', '=', batch_id))
        
        balance = self.search(domain, limit=1)
        return balance.qty_available if balance else 0.0

    @api.model
    def update_balance(self, nomenclature_id, qty_change, location_type='warehouse', 
                      warehouse_id=None, employee_id=None, location_id=None, 
                      batch_id=None, uom_id=None, company_id=None, serial_numbers=None):
        """Оновлює залишок товару"""
        if company_id is None:
            company_id = self.env.company.id
        
        if uom_id is None:
            nomenclature = self.env['product.nomenclature'].browse(nomenclature_id)
            uom_id = nomenclature.base_uom_id.id
        
        # Знаходимо або створюємо запис залишку
        domain = [
            ('nomenclature_id', '=', nomenclature_id),
            ('location_type', '=', location_type),
            ('company_id', '=', company_id),
        ]
        
        if location_type == 'warehouse':
            domain.extend([
                ('warehouse_id', '=', warehouse_id),
                ('location_id', '=', location_id or False),
            ])
        else:
            domain.append(('employee_id', '=', employee_id))
        
        if batch_id:
            domain.append(('batch_id', '=', batch_id))
        else:
            domain.append(('batch_id', '=', False))
        
        balance = self.search(domain, limit=1)
        
        if balance:
            # Оновлюємо існуючий запис
            new_qty = balance.qty_on_hand + qty_change
            
            # Логіка оновлення серійних номерів
            updated_serials = balance.serial_numbers or ''
            if serial_numbers:
                if updated_serials:
                    # Додаємо нові серійні номери до існуючих
                    existing_serials = set(balance.get_serial_numbers_list())
                    new_serials = set(serial_numbers.replace('\n', ',').split(','))
                    new_serials = [s.strip() for s in new_serials if s.strip()]
                    
                    # Фільтруємо дублікати
                    unique_new_serials = [s for s in new_serials if s not in existing_serials]
                    if unique_new_serials:
                        if updated_serials.strip():
                            updated_serials = updated_serials + '\n' + '\n'.join(unique_new_serials)
                        else:
                            updated_serials = '\n'.join(unique_new_serials)
                else:
                    updated_serials = serial_numbers
            
            balance.write({
                'qty_on_hand': new_qty,
                'last_update': fields.Datetime.now(),
                'serial_numbers': updated_serials,
            })
        else:
            # Створюємо новий запис
            if qty_change != 0:  # Створюємо тільки якщо є зміна
                vals = {
                    'nomenclature_id': nomenclature_id,
                    'location_type': location_type,
                    'qty_on_hand': qty_change,
                    'uom_id': uom_id,
                    'company_id': company_id,
                    'batch_id': batch_id or False,
                    'serial_numbers': serial_numbers,
                }
                
                if location_type == 'warehouse':
                    vals.update({
                        'warehouse_id': warehouse_id,
                        'location_id': location_id or False,
                    })
                else:
                    vals['employee_id'] = employee_id
                
                balance = self.create(vals)
        
        return balance

    def action_view_movements(self):
        """Показує рухи по цьому залишку"""
        self.ensure_one()
        domain = [
            ('nomenclature_id', '=', self.nomenclature_id.id),
            ('company_id', '=', self.company_id.id),
        ]
        
        if self.location_type == 'warehouse':
            domain.append(('warehouse_id', '=', self.warehouse_id.id))
        else:
            domain.append(('employee_id', '=', self.employee_id.id))
        
        if self.batch_id:
            domain.append(('batch_id', '=', self.batch_id.id))
        
        return {
            'name': _('Рухи товару'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.balance.movement',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'create': False},
        }