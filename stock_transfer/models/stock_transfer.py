from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from datetime import datetime


class StockTransfer(models.Model):
    _name = 'stock.transfer'
    _description = 'Переміщення товарів'
    _order = 'date desc, number desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    number = fields.Char(
        string='Номер документа',
        required=True,
        copy=False,
        readonly=True,
        default='Новий'
    )
    
    date = fields.Date(
        string='Дата документа',
        required=True,
        default=fields.Date.context_today
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Компанія',
        required=True,
        default=lambda self: self.env.company
    )
    
    warehouse_from_id = fields.Many2one(
        'stock.warehouse',
        string='Склад відправник'
    )
    
    warehouse_to_id = fields.Many2one(
        'stock.warehouse',
        string='Склад одержувач'
    )
    
    employee_from_id = fields.Many2one(
        'hr.employee',
        string='Працівник відправник'
    )
    
    employee_to_id = fields.Many2one(
        'hr.employee',
        string='Працівник одержувач'
    )
    
    transfer_type = fields.Selection([
        ('warehouse', 'Між складами'),
        ('employee', 'Між працівниками'),
        ('warehouse_employee', 'Зі складу працівнику'),
        ('employee_warehouse', 'Від працівника на склад')
    ], string='Тип переміщення', required=True, default='warehouse')
    
    state = fields.Selection([
        ('draft', 'Чернетка'),
        ('confirmed', 'Підтверджено'),
        ('done', 'Виконано'),
        ('cancelled', 'Скасовано')
    ], string='Статус', default='draft', tracking=True)
    
    line_ids = fields.One2many(
        'stock.transfer.line',
        'transfer_id',
        string='Позиції переміщення'
    )
    
    notes = fields.Text(string='Примітки')
    
    posting_datetime = fields.Datetime(
        string='Час проведення',
        readonly=True
    )
    
    no_vat = fields.Boolean(
        string='Без ПДВ',
        default=False
    )
    
    # Додаємо поле для зберігання доступних товарів на залишку
    available_stock_ids = fields.One2many(
        'stock.transfer.available.stock',
        'transfer_id',
        string='Доступні залишки',
        compute='_compute_available_stock'
    )

    @api.model
    def create(self, vals):
        if vals.get('number', 'Новий') == 'Новий':
            vals['number'] = self.env['ir.sequence'].next_by_code('stock.transfer') or 'Новий'
        return super(StockTransfer, self).create(vals)

    @api.depends('warehouse_from_id', 'employee_from_id', 'transfer_type', 'company_id')
    def _compute_available_stock(self):
        """Обчислює доступні залишки в джерелі переміщення"""
        for record in self:
            # Очищаємо попередні записи
            record.available_stock_ids = [(5, 0, 0)]
            
            if record.transfer_type in ['warehouse', 'warehouse_employee'] and record.warehouse_from_id:
                # Отримуємо залишки зі складу
                stock_data = record._get_warehouse_stock(record.warehouse_from_id, record.company_id)
            elif record.transfer_type in ['employee', 'employee_warehouse'] and record.employee_from_id:
                # Отримуємо залишки працівника
                stock_data = record._get_employee_stock(record.employee_from_id, record.company_id)
            else:
                stock_data = []
            
            # Створюємо записи доступних залишків
            available_stock_lines = []
            for stock in stock_data:
                available_stock_lines.append((0, 0, {
                    'nomenclature_id': stock['nomenclature_id'],
                    'lot_batch': stock['lot_batch'],
                    'available_qty': stock['available_qty'],
                    'location_id': stock['location_id'],
                }))
            
            record.available_stock_ids = available_stock_lines

    def _get_warehouse_stock(self, warehouse, company):
        """Отримує залишки товарів на складі для конкретної компанії"""
        # Тут потрібна логіка для отримання залишків з вашої системи
        # Припускаю, що у вас є модель для залишків або зв'язок з stock.quant
        
        # Приклад запиту (адаптуйте під вашу структуру):
        stock_data = []
        
        # Якщо у вас є модель stock.balance або подібна
        if hasattr(self.env, 'stock.balance'):
            balances = self.env['stock.balance'].search([
                ('warehouse_id', '=', warehouse.id),
                ('company_id', '=', company.id),
                ('qty_available', '>', 0)
            ])
            
            for balance in balances:
                stock_data.append({
                    'nomenclature_id': balance.nomenclature_id.id,
                    'lot_batch': balance.lot_batch or 'Без партії',
                    'available_qty': balance.qty_available,
                    'location_id': balance.location_id.id if balance.location_id else False,
                })
        
        # Альтернатива через stock.quant (якщо використовуєте стандартні stock модулі)
        else:
            quants = self.env['stock.quant'].search([
                ('location_id.warehouse_id', '=', warehouse.id),
                ('company_id', '=', company.id),
                ('quantity', '>', 0)
            ])
            
            for quant in quants:
                # Знаходимо відповідну номенклатуру
                nomenclature = self.env['product.nomenclature'].search([
                    ('name', '=', quant.product_id.name)  # або інший зв'язок
                ], limit=1)
                
                if nomenclature:
                    stock_data.append({
                        'nomenclature_id': nomenclature.id,
                        'lot_batch': quant.lot_id.name if quant.lot_id else 'Без партії',
                        'available_qty': quant.quantity,
                        'location_id': quant.location_id.id,
                    })
        
        return stock_data

    def _get_employee_stock(self, employee, company):
        """Отримує залишки товарів у працівника"""
        # Тут логіка для отримання залишків працівника
        # Можливо у вас є окрема модель employee.stock або подібна
        stock_data = []
        
        if hasattr(self.env, 'employee.stock'):
            employee_stock = self.env['employee.stock'].search([
                ('employee_id', '=', employee.id),
                ('company_id', '=', company.id),
                ('qty_available', '>', 0)
            ])
            
            for stock in employee_stock:
                stock_data.append({
                    'nomenclature_id': stock.nomenclature_id.id,
                    'lot_batch': stock.lot_batch or 'Без партії',
                    'available_qty': stock.qty_available,
                    'location_id': False,  # Працівники можуть не мати фізичних локацій
                })
        
        return stock_data

    def action_confirm(self):
        # Перевіряємо залишки перед підтвердженням
        for line in self.line_ids:
            line._validate_stock_availability()
        self.state = 'confirmed'
        
    def action_done(self):
        # Останнім разом перевіряємо залишки перед проведенням
        for line in self.line_ids:
            line._validate_stock_availability()
        self.state = 'done'
        self.posting_datetime = datetime.now()
        
    def action_cancel(self):
        self.state = 'cancelled'
        
    def action_draft(self):
        self.state = 'draft'
        self.posting_datetime = False

    @api.onchange('transfer_type', 'warehouse_from_id', 'employee_from_id', 'company_id')
    def _onchange_source_params(self):
        """При зміні джерела переміщення очищаємо позиції"""
        if self.line_ids:
            # Попереджаємо користувача про очищення позицій
            return {
                'warning': {
                    'title': 'Увага!',
                    'message': 'Зміна джерела переміщення призведе до очищення вже доданих позицій. Продовжити?'
                }
            }

    @api.onchange('transfer_type')
    def _onchange_transfer_type(self):
        # Очищаємо поля залежно від типу переміщення
        if self.transfer_type == 'warehouse':
            self.employee_from_id = False
            self.employee_to_id = False
        elif self.transfer_type == 'employee':
            self.warehouse_from_id = False
            self.warehouse_to_id = False
        elif self.transfer_type == 'warehouse_employee':
            self.employee_from_id = False
            self.warehouse_to_id = False
        elif self.transfer_type == 'employee_warehouse':
            self.warehouse_from_id = False
            self.employee_to_id = False
        
        # Очищаємо позиції при зміні типу
        self.line_ids = [(5, 0, 0)]


class StockTransferLine(models.Model):
    _name = 'stock.transfer.line'
    _description = 'Позиція переміщення'

    transfer_id = fields.Many2one(
        'stock.transfer',
        string='Переміщення',
        required=True,
        ondelete='cascade'
    )
    
    nomenclature_id = fields.Many2one(
        'product.nomenclature',
        string='Номенклатура',
        required=True,
        domain="[('id', 'in', available_nomenclature_ids)]"
    )
    
    # Додаємо поле для фільтрації доступних товарів
    available_nomenclature_ids = fields.Many2many(
        'product.nomenclature',
        compute='_compute_available_nomenclature',
        string='Доступні товари'
    )
    
    lot_batch = fields.Char(
        string='Партія/Лот',
        help='Партія або лот товару'
    )
    
    available_batches = fields.Char(
        string='Доступні партії',
        compute='_compute_available_batches',
        help='Показує доступні партії для вибраного товару'
    )
    
    selected_uom_id = fields.Many2one(
        'uom.uom',
        string='Одиниця виміру',
        required=True
    )
    
    qty = fields.Float(
        string='Кількість',
        required=True,
        default=1.0
    )
    
    max_available_qty = fields.Float(
        string='Максимально доступно',
        compute='_compute_max_available_qty',
        help='Максимальна доступна кількість для вибраної партії'
    )
    
    price_unit_no_vat = fields.Float(
        string='Ціна без ПДВ',
        default=0.0
    )
    
    vat_rate = fields.Float(
        string='Ставка ПДВ',
        default=20.0
    )
    
    amount_no_vat = fields.Float(
        string='Сума без ПДВ',
        compute='_compute_amounts',
        store=True
    )
    
    vat_amount = fields.Float(
        string='Сума ПДВ',
        compute='_compute_amounts',
        store=True
    )
    
    amount_with_vat = fields.Float(
        string='Сума з ПДВ',
        compute='_compute_amounts',
        store=True
    )

    @api.depends('transfer_id.available_stock_ids')
    def _compute_available_nomenclature(self):
        """Обчислює список доступних товарів на залишку"""
        for line in self:
            if line.transfer_id.available_stock_ids:
                available_ids = line.transfer_id.available_stock_ids.mapped('nomenclature_id').ids
                line.available_nomenclature_ids = [(6, 0, available_ids)]
            else:
                line.available_nomenclature_ids = [(6, 0, [])]

    @api.depends('nomenclature_id', 'transfer_id.available_stock_ids')
    def _compute_available_batches(self):
        """Показує доступні партії для вибраного товару"""
        for line in self:
            if line.nomenclature_id and line.transfer_id.available_stock_ids:
                batches = line.transfer_id.available_stock_ids.filtered(
                    lambda x: x.nomenclature_id.id == line.nomenclature_id.id
                ).mapped('lot_batch')
                line.available_batches = ', '.join(batches) if batches else 'Партії відсутні'
            else:
                line.available_batches = ''

    @api.depends('nomenclature_id', 'lot_batch', 'transfer_id.available_stock_ids')
    def _compute_max_available_qty(self):
        """Обчислює максимальну доступну кількість для вибраної партії"""
        for line in self:
            if line.nomenclature_id and line.transfer_id.available_stock_ids:
                stock_record = line.transfer_id.available_stock_ids.filtered(
                    lambda x: x.nomenclature_id.id == line.nomenclature_id.id and 
                             x.lot_batch == line.lot_batch
                )
                line.max_available_qty = stock_record.available_qty if stock_record else 0
            else:
                line.max_available_qty = 0

    @api.depends('qty', 'price_unit_no_vat', 'vat_rate')
    def _compute_amounts(self):
        for line in self:
            line.amount_no_vat = line.qty * line.price_unit_no_vat
            line.vat_amount = line.amount_no_vat * line.vat_rate / 100
            line.amount_with_vat = line.amount_no_vat + line.vat_amount

    @api.onchange('nomenclature_id')
    def _onchange_nomenclature_id(self):
        if self.nomenclature_id:
            # Встановлюємо одиницю виміру
            if hasattr(self.nomenclature_id, 'base_uom_id'):
                self.selected_uom_id = self.nomenclature_id.base_uom_id
            
            # Очищаємо партію при зміні товару
            self.lot_batch = False
            self.qty = 1.0
            
            # Встановлюємо ціну якщо є
            if hasattr(self.nomenclature_id, 'price_usd'):
                self.price_unit_no_vat = self.nomenclature_id.price_usd

    @api.onchange('lot_batch')
    def _onchange_lot_batch(self):
        """При зміні партії оновлюємо максимальну кількість"""
        if self.lot_batch and self.max_available_qty > 0:
            # Пропонуємо взяти всю партію
            if self.max_available_qty != self.qty:
                return {
                    'warning': {
                        'title': 'Доступна кількість',
                        'message': f'Доступно {self.max_available_qty} од. Бажаєте взяти всю партію?'
                    }
                }

    def action_take_full_batch(self):
        """Кнопка для взяття повної партії"""
        self.ensure_one()
        if self.max_available_qty > 0:
            self.qty = self.max_available_qty

    def _validate_stock_availability(self):
        """Перевіряє чи достатньо товару на залишку"""
        self.ensure_one()
        if self.qty > self.max_available_qty:
            raise ValidationError(
                f'Недостатньо товару "{self.nomenclature_id.name}" '
                f'партії "{self.lot_batch}" на залишку!\n'
                f'Потрібно: {self.qty}\n'
                f'Доступно: {self.max_available_qty}'
            )

    @api.constrains('qty')
    def _check_qty_constraints(self):
        """Перевірки кількості"""
        for line in self:
            if line.qty <= 0:
                raise ValidationError('Кількість має бути більшою за нуль!')
            
            if line.transfer_id.state in ['confirmed', 'done'] and line.qty > line.max_available_qty:
                raise ValidationError(
                    f'Недостатньо товару "{line.nomenclature_id.name}" на залишку!'
                )


class StockTransferAvailableStock(models.TransientModel):
    """Модель для зберігання доступних залишків"""
    _name = 'stock.transfer.available.stock'
    _description = 'Доступні залишки для переміщення'

    transfer_id = fields.Many2one(
        'stock.transfer',
        string='Переміщення',
        required=True,
        ondelete='cascade'
    )
    
    nomenclature_id = fields.Many2one(
        'product.nomenclature',
        string='Номенклатура',
        required=True
    )
    
    lot_batch = fields.Char(
        string='Партія/Лот'
    )
    
    available_qty = fields.Float(
        string='Доступна кількість'
    )
    
    location_id = fields.Many2one(
        'stock.location',
        string='Локація'
    )