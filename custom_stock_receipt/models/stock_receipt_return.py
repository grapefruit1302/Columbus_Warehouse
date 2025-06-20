from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime


class StockReceiptReturn(models.Model):
    _name = 'stock.receipt.return'
    _description = 'Повернення з сервісу'
    _order = 'date desc, id desc'
    _rec_name = 'number'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    number = fields.Char('Номер', required=True, copy=False, readonly=True, 
                        index=True, default=lambda self: self.env['ir.sequence'].next_by_code('stock.receipt.return'))
    date = fields.Datetime('Дата', required=True, default=fields.Datetime.now)
    service_partner_id = fields.Many2one('res.partner', 'Сервісний центр', required=True)
    warehouse_id = fields.Many2one('stock.warehouse', 'Склад', required=True,
                                  default=lambda self: self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1))
    
    state = fields.Selection([
        ('draft', 'Чернетка'),
        ('confirmed', 'Підтверджено'),
        ('done', 'Виконано'),
        ('cancel', 'Скасовано')
    ], 'Статус', default='draft', tracking=True)
    
    line_ids = fields.One2many('stock.receipt.return.line', 'return_id', 'Позиції')
    service_notes = fields.Text('Примітки сервісу')
    notes = fields.Text('Внутрішні примітки')
    
    total_qty = fields.Float('Загальна кількість', compute='_compute_totals', store=True)
    
    @api.depends('line_ids.qty')
    def _compute_totals(self):
        for record in self:
            record.total_qty = sum(line.qty for line in record.line_ids)
    
    def action_confirm(self):
        if not self.line_ids:
            raise UserError('Додайте хоча б одну позицію до документа!')
        self.state = 'confirmed'
        
    def action_done(self):
        self.state = 'done'
        
    def action_cancel(self):
        self.state = 'cancel'
        
    def action_reset_to_draft(self):
        self.state = 'draft'


class StockReceiptReturnLine(models.Model):
    _name = 'stock.receipt.return.line'
    _description = 'Позиція повернення з сервісу'

    return_id = fields.Many2one('stock.receipt.return', 'Повернення', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', 'Товар', required=True)
    product_uom_id = fields.Many2one('uom.uom', 'Од. виміру', related='product_id.uom_id')
    qty = fields.Float('Кількість', default=1.0, required=True)
    location_id = fields.Many2one('stock.location', 'Локація', required=True)
    lot_ids = fields.Many2many('stock.lot', string='Серійні номери/Лоти')
    service_status = fields.Selection([
        ('repaired', 'Відремонтовано'),
        ('replaced', 'Замінено'),
        ('no_repair', 'Без ремонту')
    ], 'Статус сервісу')
    notes = fields.Char('Примітки')