# stock_transfer/models/stock_transfer.py

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

    @api.model
    def create(self, vals):
        if vals.get('number', 'Новий') == 'Новий':
            vals['number'] = self.env['ir.sequence'].next_by_code('stock.transfer') or 'Новий'
        return super(StockTransfer, self).create(vals)

    def action_confirm(self):
        self.state = 'confirmed'
        
    def action_done(self):
        self.state = 'done'
        self.posting_datetime = fields.Datetime.now()
        
    def action_cancel(self):
        self.state = 'cancelled'
        
    def action_draft(self):
        self.state = 'draft'
        self.posting_datetime = False

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

    @api.onchange('warehouse_from_id', 'employee_from_id')
    def _onchange_from_location(self):
        """При зміні відправника очищаємо позиції"""
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
    
    # Поле для фільтрації доступної номенклатури
    available_nomenclature_ids = fields.Many2many(
        'product.nomenclature',
        compute='_compute_available_nomenclature',
        string='Доступна номенклатура'
    )
    
    selected_uom_id = fields.Many2one(
        'uom.uom',
        string='Одиниця виміру',
        required=True
    )
    
    qty = fields.Float(
        string='Кількість',
        required=True,
        default=1.0,
        digits='Product Unit of Measure'
    )
    
    # Поле для відображення доступної кількості
    available_qty = fields.Float(
        'Доступна кількість',
        compute='_compute_available_qty',
        help='Доступна кількість в локації відправника'
    )
    
    # Поля для відображення партій (тільки для читання)
    batch_info = fields.Text(
        'Інформація про партії',
        compute='_compute_batch_info',
        help='Показує які партії будуть використані по FIFO'
    )

    @api.depends('transfer_id.transfer_type', 'transfer_id.warehouse_from_id', 
                 'transfer_id.employee_from_id', 'transfer_id.company_id')
    def _compute_available_nomenclature(self):
        """Обчислює доступну номенклатуру в залежності від локації відправника"""
        for line in self:
            if not line.transfer_id:
                line.available_nomenclature_ids = [(6, 0, [])]
                continue
                
            transfer = line.transfer_id
            Balance = self.env['stock.balance']
            
            # Визначаємо параметри для пошуку
            domain = [
                ('company_id', '=', transfer.company_id.id),
                ('qty_available', '>', 0),
            ]
            
            if transfer.transfer_type in ['warehouse', 'warehouse_employee']:
                if transfer.warehouse_from_id:
                    domain.extend([
                        ('location_type', '=', 'warehouse'),
                        ('warehouse_id', '=', transfer.warehouse_from_id.id)
                    ])
                else:
                    line.available_nomenclature_ids = [(6, 0, [])]
                    continue
            elif transfer.transfer_type in ['employee', 'employee_warehouse']:
                if transfer.employee_from_id:
                    domain.extend([
                        ('location_type', '=', 'employee'),
                        ('employee_id', '=', transfer.employee_from_id.id)
                    ])
                else:
                    line.available_nomenclature_ids = [(6, 0, [])]
                    continue
            else:
                line.available_nomenclature_ids = [(6, 0, [])]
                continue
            
            # Знаходимо всі залишки з товарами
            balances = Balance.search(domain)
            nomenclature_ids = balances.mapped('nomenclature_id.id')
            
            line.available_nomenclature_ids = [(6, 0, nomenclature_ids)]

    @api.depends('nomenclature_id', 'transfer_id.transfer_type', 
                 'transfer_id.warehouse_from_id', 'transfer_id.employee_from_id')
    def _compute_available_qty(self):
        """Обчислює доступну кількість товару"""
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

    @api.depends('nomenclature_id', 'qty', 'transfer_id.transfer_type',
                 'transfer_id.warehouse_from_id', 'transfer_id.employee_from_id')
    def _compute_batch_info(self):
        """Показує інформацію про партії, які будуть використані"""
        for line in self:
            if not line.nomenclature_id or not line.qty or not line.transfer_id:
                line.batch_info = ''
                continue
                
            Balance = self.env['stock.balance']
            transfer = line.transfer_id
            
            # Отримуємо FIFO партії
            if transfer.transfer_type in ['warehouse', 'warehouse_employee']:
                if not transfer.warehouse_from_id:
                    line.batch_info = 'Не вказано склад відправник'
                    continue
                    
                fifo_balances, remaining_qty = Balance.get_fifo_balances(
                    nomenclature_id=line.nomenclature_id.id,
                    required_qty=line.qty,
                    location_type='warehouse',
                    warehouse_id=transfer.warehouse_from_id.id,
                    company_id=transfer.company_id.id
                )
            elif transfer.transfer_type in ['employee', 'employee_warehouse']:
                if not transfer.employee_from_id:
                    line.batch_info = 'Не вказано працівника відправника'
                    continue
                    
                fifo_balances, remaining_qty = Balance.get_fifo_balances(
                    nomenclature_id=line.nomenclature_id.id,
                    required_qty=line.qty,
                    location_type='employee',
                    employee_id=transfer.employee_from_id.id,
                    company_id=transfer.company_id.id
                )
            else:
                line.batch_info = 'Невідомий тип переміщення'
                continue
            
            # Формуємо текст з інформацією про партії
            batch_lines = []
            for fifo_item in fifo_balances:
                balance = fifo_item['balance']
                qty = fifo_item['qty']
                
                if balance.batch_id:
                    batch_lines.append(f"Партія {balance.batch_id.batch_number}: {qty} {balance.uom_id.name}")
                else:
                    batch_lines.append(f"Без партії: {qty} {balance.uom_id.name}")
            
            if remaining_qty > 0:
                batch_lines.append(f"⚠️ Недостатньо: {remaining_qty} {line.selected_uom_id.name or ''}")
            
            line.batch_info = '\n'.join(batch_lines) if batch_lines else 'Немає доступних партій'

    @api.onchange('nomenclature_id')
    def _onchange_nomenclature_id(self):
        """При зміні номенклатури встановлюємо одиницю виміру"""
        if self.nomenclature_id:
            # Знаходимо основну одиницю виміру
            if hasattr(self.nomenclature_id, 'uom_line_ids'):
                default_uom = self.nomenclature_id.uom_line_ids.filtered('is_default')
                if default_uom:
                    self.selected_uom_id = default_uom[0].uom_id
                elif self.nomenclature_id.uom_line_ids:
                    self.selected_uom_id = self.nomenclature_id.uom_line_ids[0].uom_id

    @api.constrains('qty', 'nomenclature_id')
    def _check_qty_availability(self):
        """Перевіряє доступність товару при зміні кількості"""
        for line in self:
            if line.qty > 0 and line.available_qty < line.qty:
                raise ValidationError(
                    f'Недостатньо товару "{line.nomenclature_id.name}". '
                    f'Доступно: {line.available_qty}, потрібно: {line.qty}'
                )