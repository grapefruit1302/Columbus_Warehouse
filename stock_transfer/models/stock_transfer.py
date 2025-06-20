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
        required=True
    )
    
    lot_batch = fields.Char(
        string='Партія/Лот',
        help='Партія або лот товару'
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
            
            # Встановлюємо ціну якщо є
            if hasattr(self.nomenclature_id, 'price_usd'):
                self.price_unit_no_vat = self.nomenclature_id.price_usd