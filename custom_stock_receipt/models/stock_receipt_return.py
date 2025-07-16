from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime

from ..services.numbering_service import NumberingService


class StockReceiptReturn(models.Model):
    _name = 'stock.receipt.return'
    _description = 'Повернення з сервісу'
    _order = 'date desc, id desc'
    _rec_name = 'number'
    _inherit = [
        'stock.receipt.base',
        'serial.tracking.mixin',
        'document.validation.mixin',
        'workflow.mixin'
    ]

    service_partner_id = fields.Many2one('res.partner', 'Сервісний центр', required=True)
    line_ids = fields.One2many('stock.receipt.return.line', 'return_id', 'Позиції')
    service_notes = fields.Text('Примітки сервісу')
    total_qty = fields.Float('Загальна кількість', compute='_compute_totals', store=True)
    
    @api.depends('line_ids.qty')
    def _compute_totals(self):
        for record in self:
            record.total_qty = sum(line.qty for line in record.line_ids)

    @api.model
    def create(self, vals):
        """Генеруємо номер документа при створенні"""
        if not vals.get('number') or vals.get('number') in ['/', 'Новий']:
            vals['number'] = NumberingService.generate_receipt_number('return', self.env)
        return super(StockReceiptReturn, self).create(vals)


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
