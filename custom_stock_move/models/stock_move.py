from odoo import fields, models

class StockMove(models.Model):
    _inherit = 'stock.move'

    coefficient = fields.Float(string='Coefficient', default=1.0)

    price_excl_vat = fields.Float(string='Price Excl. VAT')