from odoo import models, fields, api, _

class StockReceiptIncoming(models.Model):
    _inherit = 'stock.receipt.incoming'

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
        for receipt in self:
            batches = self.env['stock.batch'].search([
                ('source_document_type', '=', 'receipt'),
                ('source_document_number', '=', receipt.number)
            ])
            receipt.batch_ids = batches
            receipt.batch_count = len(batches)

    def _do_posting(self, posting_time, custom_datetime=None):
        """Розширюємо метод проведення для створення партій"""
        result = super()._do_posting(posting_time, custom_datetime)
        
        # Створюємо партії для кожної позиції
        for line in self.line_ids:
            self._create_batch_for_line(line)
        
        return result

    def _create_batch_for_line(self, line):
        """Створює партію для позиції накладної"""
        if line.qty <= 0:
            return
        
        # Отримуємо локацію (якщо не вказана, використовуємо основну локацію складу)
        location = line.location_id or self.warehouse_id.lot_stock_id
        
        try:
            batch = self.env['stock.batch'].create_batch_from_receipt(
                nomenclature_id=line.nomenclature_id.id,
                receipt_number=self.number,
                qty=line.qty,
                uom_id=line.selected_uom_id.id or line.product_uom_id.id,
                location_id=location.id,
                company_id=self.company_id.id,
                date_created=self.posting_datetime,
                serial_numbers=line.serial_numbers if line.tracking_serial else None,
            )
            
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
        """Відкриває партії, створені з цієї накладної"""
        self.ensure_one()
        return {
            'name': _('Партії накладної %s') % self.number,
            'type': 'ir.actions.act_window',
            'res_model': 'stock.batch',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.batch_ids.ids)],
            'context': {'create': False},
        }