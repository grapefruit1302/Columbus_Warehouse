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

    serial_count = fields.Integer(
        'Кількість серійних номерів', 
        compute='_compute_serial_count',
        help='Кількість серійних номерів у цьому залишку'
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
        help='Кількість доступна для операцій'
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
    
    # ДОДАЄМО поле для відображення серійних номерів у вигляді списку
    serial_line_ids = fields.One2many(
        'stock.balance.serial.line', 
        'balance_id', 
        'Серійні номери',
        compute='_compute_serial_lines'
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
    def _compute_serial_count(self):
        """Підраховує кількість серійних номерів"""
        for balance in self:
            balance.serial_count = len(balance._get_serial_numbers_list())

    @api.depends('serial_numbers', 'batch_id')
    @api.depends('serial_numbers')
    def _compute_serial_lines(self):
        """Створює тимчасові записи для відображення серійних номерів"""
        for balance in self:
            # Видаляємо існуючі записи
            balance.serial_line_ids.unlink()
            
            if balance.serial_numbers:
                serials = balance._get_serial_numbers_list()
                lines_to_create = []
                
                for serial in serials:
                    lines_to_create.append({
                        'balance_id': balance.id,
                        'serial_number': serial,
                        'batch_number': balance.batch_id.batch_number if balance.batch_id else '',
                        'document_reference': balance.batch_id.source_document_number if balance.batch_id else '',
                        'source_document_type': self._get_doc_type_display(balance.batch_id.source_document_type) if balance.batch_id else '',
                        'date_created': balance.batch_id.date_created if balance.batch_id else False,
                    })
                
                # Створюємо нові записи
                for line_data in lines_to_create:
                    self.env['stock.balance.serial.line'].create(line_data)

    # ДОДАЙТЕ ці методи:
    def _get_doc_type_display(self, doc_type):
        """Перекладає тип документу"""
        mapping = {
            'receipt': 'Прихідна накладна',
            'inventory': 'Акт оприходування', 
            'return': 'Повернення з сервісу',
        }
        return mapping.get(doc_type, doc_type or '')



    def action_view_serials(self):
        """Швидкий перегляд серійних номерів з списку"""
        self.ensure_one()
        
        if not self.serial_numbers:
            raise UserError(_('У цього залишку немає серійних номерів для відображення.'))
        
        # Відкриваємо форму залишку
        return {
            'name': _('Серійні номери: %s') % self.nomenclature_id.name,
            'type': 'ir.actions.act_window',
            'res_model': 'stock.balance',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


    @api.depends('serial_numbers')
    def _compute_serial_count(self):
        """Підраховує кількість серійних номерів"""
        for balance in self:
            balance.serial_count = len(balance._get_serial_numbers_list())

    def _get_serial_info(self, serial_number):
        """Отримує додаткову інформацію про серійний номер"""
        result = {
            'batch_number': '',
            'document_reference': '',
            'source_document_type': '',
            'date_created': False,
        }
        
        # Якщо є партія, отримуємо інформацію з неї
        if self.batch_id:
            batch = self.batch_id
            result.update({
                'batch_number': batch.batch_number,
                'document_reference': batch.source_document_number or '',
                'date_created': batch.date_created,
            })
            
            # Перекладаємо тип документу
            doc_type_mapping = {
                'receipt': 'Прихідна накладна',
                'inventory': 'Акт оприходування', 
                'return': 'Повернення з сервісу',
            }
            result['source_document_type'] = doc_type_mapping.get(
                batch.source_document_type, batch.source_document_type or ''
            )
        
        return result

    def _get_serial_numbers_list(self):
        """Повертає список серійних номерів (виправлений метод)"""
        if not self.serial_numbers:
            return []
        
        serials = []
        # Розділяємо по новому рядку, потім по комі
        for line in self.serial_numbers.split('\n'):
            for serial in line.split(','):
                serial = serial.strip()
                if serial:  # Ігноруємо порожні рядки
                    serials.append(serial)
        return serials

    @api.depends('qty_on_hand', 'nomenclature_id.tracking_serial', 'serial_numbers')
    def _compute_available_qty(self):
        """Обчислює доступну кількість товару з урахуванням серійних номерів"""
        for balance in self:
            _logger.info(f"🔄 Computing qty_available for {balance.nomenclature_id.name}")
            _logger.info(f"   📊 qty_on_hand: {balance.qty_on_hand}")
            _logger.info(f"   🏷️ tracking_serial: {balance.nomenclature_id.tracking_serial}")
            _logger.info(f"   📋 serial_numbers: {balance.serial_numbers}")
            
            # Якщо товар обліковується по серійних номерах
            if balance.nomenclature_id.tracking_serial:
                # Доступна кількість = кількість серійних номерів
                serial_count = len(balance._get_serial_numbers_list())
                balance.qty_available = serial_count
                _logger.info(f"   ✅ Serial tracking: qty_available = {serial_count}")
            else:
                # Для звичайних товарів - доступна кількість = фізичній кількості
                balance.qty_available = balance.qty_on_hand
                _logger.info(f"   ✅ Regular tracking: qty_available = {balance.qty_on_hand}")


    def _get_serial_numbers_list(self):
        """Повертає список серійних номерів"""
        if not self.serial_numbers:
            return []
        
        serials = []
        for line in self.serial_numbers.split('\n'):
            for serial in line.split(','):
                serial = serial.strip()
                if serial:
                    serials.append(serial)
        return serials

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
        """Оновлює залишок товару з правильним додаванням серійних номерів"""
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
            
            # ПРАВИЛЬНО обробляємо серійні номери
            existing_serials = balance._get_serial_numbers_list()
            if serial_numbers and qty_change > 0:  # Додаємо серійні номери при надходженні
                new_serials = []
                for line in serial_numbers.split('\n'):
                    for serial in line.split(','):
                        serial = serial.strip()
                        if serial and serial not in existing_serials:
                            new_serials.append(serial)
                
                all_serials = existing_serials + new_serials
                combined_serials = '\n'.join(all_serials) if all_serials else balance.serial_numbers
            else:
                combined_serials = balance.serial_numbers
            
            balance.write({
                'qty_on_hand': new_qty,
                'last_update': fields.Datetime.now(),
                'serial_numbers': combined_serials,
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

    @api.model
    def get_available_qty(self, nomenclature_id, location_type='warehouse', 
                         warehouse_id=None, employee_id=None, batch_id=None, company_id=None):
        """Отримує доступну кількість товару"""
        return self.get_balance(
            nomenclature_id=nomenclature_id,
            location_type=location_type,
            warehouse_id=warehouse_id,
            employee_id=employee_id,
            batch_id=batch_id,
            company_id=company_id
        )

    @api.model
    def check_availability(self, nomenclature_id, required_qty, location_type='warehouse',
                          warehouse_id=None, employee_id=None, batch_id=None, company_id=None):
        """Перевіряє доступність товару для операції"""
        available_qty = self.get_available_qty(
            nomenclature_id=nomenclature_id,
            location_type=location_type,
            warehouse_id=warehouse_id,
            employee_id=employee_id,
            batch_id=batch_id,
            company_id=company_id
        )
        
        return available_qty >= required_qty

    @api.model
    def get_fifo_balances(self, nomenclature_id, required_qty, location_type='warehouse',
                         warehouse_id=None, employee_id=None, company_id=None):
        """Отримує залишки за FIFO принципом для списання"""
        if company_id is None:
            company_id = self.env.company.id
        
        domain = [
            ('nomenclature_id', '=', nomenclature_id),
            ('location_type', '=', location_type),
            ('company_id', '=', company_id),
            ('qty_available', '>', 0),
        ]
        
        if location_type == 'warehouse':
            domain.append(('warehouse_id', '=', warehouse_id))
        else:
            domain.append(('employee_id', '=', employee_id))
        
        # Сортуємо за датою створення партії (FIFO)
        balances = self.search(domain, order='batch_id.date_created ASC, id ASC')
        
        fifo_list = []
        remaining_qty = required_qty
        
        for balance in balances:
            if remaining_qty <= 0:
                break
            
            available = min(balance.qty_available, remaining_qty)
            if available > 0:
                fifo_list.append({
                    'balance': balance,
                    'qty': available,
                })
                remaining_qty -= available
        
        return fifo_list, remaining_qty

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



class StockBalanceSerialLine(models.TransientModel):
    _name = 'stock.balance.serial.line'
    _description = 'Серійний номер у залишках'

    balance_id = fields.Many2one('stock.balance', 'Залишок', required=True, ondelete='cascade')
    serial_number = fields.Char('Серійний номер', required=True)
    batch_number = fields.Char('Партія')
    document_reference = fields.Char('Документ')
    source_document_type = fields.Char('Тип документу')
    date_created = fields.Datetime('Дата створення')