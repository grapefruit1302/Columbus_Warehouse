from odoo import models, fields, api, _

class StockReceiptDisposal(models.Model):
    _inherit = 'stock.receipt.disposal'

    batch_ids = fields.One2many(
        'stock.batch', 
        compute='_compute_batch_ids',
        string='Створені партії'
    )
    
    batch_count = fields.Integer(
        'Кількість партій',
        compute='_compute_batch_ids'
    )

    def _compute_batch_ids(self):
        for disposal in self:
            batches = self.env['stock.batch'].search([
                ('source_document_type', '=', 'inventory'),
                ('source_document_number', '=', disposal.number)
            ])
            disposal.batch_ids = batches
            disposal.batch_count = len(batches)

    def _do_posting(self, posting_time, custom_datetime=None):
        """Розширюємо метод проведення для створення партій"""
        result = super()._do_posting(posting_time, custom_datetime)
        
        # Створюємо партії для кожної позиції
        for line in self.line_ids:
            self._create_batch_for_line(line)
        
        return result

    def _create_batch_for_line(self, line):
        """Створює партію для позиції акта"""
        if line.qty <= 0:
            return
        
        # Отримуємо локацію (якщо не вказана, використовуємо основну локацію складу)
        location = line.location_id or self.warehouse_id.lot_stock_id
        
        try:
            # Створюємо нову партію
            batch_vals = {
                'batch_number': f"{self.number}-{line.id}",
                'nomenclature_id': line.nomenclature_id.id,
                'source_document_type': 'inventory',
                'source_document_number': self.number,
                'initial_qty': line.qty,
                'current_qty': line.qty,
                'uom_id': line.selected_uom_id.id or line.product_uom_id.id,
                'location_id': location.id,
                'company_id': self.company_id.id,
                'date_created': self.posting_datetime or fields.Datetime.now(),
                'serial_numbers': line.serial_numbers if line.tracking_serial else None,
            }
            
            batch = self.env['stock.batch'].create(batch_vals)
            
            # Створюємо рух для партії
            self.env['stock.batch.movement'].create({
                'batch_id': batch.id,
                'movement_type': 'in',
                'operation_type': 'inventory',
                'qty': line.qty,
                'uom_id': batch.uom_id.id,
                'location_to_id': location.id,
                'document_reference': self.number,
                'date': self.posting_datetime or fields.Datetime.now(),
                'company_id': self.company_id.id,
                'notes': f'Створення партії з акту оприходування {self.number}',
            })
            
            self.message_post(
                body=_('Створено партію %s для %s: %s %s') % 
                     (batch.batch_number, line.nomenclature_id.name, line.qty, 
                      (line.selected_uom_id or line.product_uom_id).name),
                message_type='notification'
            )
            
        except Exception as e:
            self.message_post(
                body=_('Помилка створення партії для %s: %s') % (line.nomenclature_id.name, str(e)),
                message_type='notification'
            )

    def action_view_batches(self):
        """Відкриває партії, створені з цього акта"""
        self.ensure_one()
        return {
            'name': _('Партії акта %s') % self.number,
            'type': 'ir.actions.act_window',
            'res_model': 'stock.batch',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.batch_ids.ids)],
            'context': {'create': False},
        }
