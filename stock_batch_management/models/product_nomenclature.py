from odoo import models, fields, api, _

class ProductNomenclature(models.Model):
    _inherit = 'product.nomenclature'

    batch_ids = fields.One2many(
        'stock.batch', 
        'nomenclature_id', 
        'Партії'
    )
    
    batch_count = fields.Integer(
        'Кількість партій',
        compute='_compute_batch_count'
    )
    
    total_qty_in_batches = fields.Float(
        'Загальна кількість в партіях',
        compute='_compute_batch_totals',
        digits='Product Unit of Measure'
    )
    
    available_qty_in_batches = fields.Float(
        'Доступна кількість в партіях',
        compute='_compute_batch_totals',
        digits='Product Unit of Measure'
    )

    @api.depends('batch_ids')
    def _compute_batch_count(self):
        for product in self:
            product.batch_count = len(product.batch_ids.filtered(lambda b: b.state == 'active'))

    @api.depends('batch_ids.current_qty', 'batch_ids.available_qty', 'batch_ids.state')
    def _compute_batch_totals(self):
        for product in self:
            active_batches = product.batch_ids.filtered(lambda b: b.state == 'active')
            product.total_qty_in_batches = sum(active_batches.mapped('current_qty'))
            product.available_qty_in_batches = sum(active_batches.mapped('available_qty'))

    def action_view_batches(self):
        """Відкриває партії номенклатури"""
        self.ensure_one()
        return {
            'name': _('Партії %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'stock.batch',
            'view_mode': 'list,form',
            'domain': [('nomenclature_id', '=', self.id)],
            'context': {'default_nomenclature_id': self.id, 'create': False},
        }

    def get_available_batches_fifo(self, location_id, qty_needed):
        """Повертає доступні партії за FIFO для вказаної кількості"""
        return self.env['stock.batch'].get_fifo_batches(
            nomenclature_id=self.id,
            location_id=location_id,
            qty_needed=qty_needed
        )