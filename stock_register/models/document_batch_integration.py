from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class DocumentBatchIntegration(models.AbstractModel):
    """Інтеграція документів з віртуальними партіями"""
    _name = 'document.batch.integration'
    _description = 'Базова інтеграція документів з партіями'

    # ЗБЕРЕЖЕНІ existing поля для партій
    batch_ids = fields.One2many(
        'stock.batch.virtual',
        compute='_compute_batch_ids',
        string='Створені партії'
    )
    
    batch_count = fields.Integer(
        'Кількість партій',
        compute='_compute_batch_ids'
    )

    @api.depends('number', 'state')
    def _compute_batch_ids(self):
        """Обчислює партії створені цим документом"""
        for record in self:
            if record.number:
                # Шукаємо партії створені цим документом через регістр
                domain = [
                    ('source_document_number', '=', record.number),
                ]
                
                # Додаємо фільтр по типу документа якщо є
                if hasattr(record, '_name'):
                    domain.append(('source_document_type', 'like', record._name))
                
                batch_virtual_model = record.env['stock.batch.virtual']
                batches = batch_virtual_model.search(domain)
                
                record.batch_ids = batches
                record.batch_count = len(batches)
            else:
                record.batch_ids = record.env['stock.batch.virtual']
                record.batch_count = 0

    def action_view_batches(self):
        """ЗБЕРЕЖЕНИЙ existing метод - відкриває партії документа"""
        self.ensure_one()
        
        domain = [
            ('source_document_number', '=', self.number),
        ]
        
        # Додаємо фільтр по типу документа
        if hasattr(self, '_name'):
            domain.append(('source_document_type', 'like', self._name))
        
        return {
            'name': _('Партії документа %s') % self.number,
            'type': 'ir.actions.act_window',
            'res_model': 'stock.batch.virtual',  # Тепер через віртуальну модель
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'search_default_active': 1,
            },
            'target': 'current',
        }


class StockReceiptIncomingBatchIntegration(models.Model):
    """Інтеграція прихідних накладних з віртуальними партіями"""
    _name = 'stock.receipt.incoming'
    _inherit = ['stock.receipt.incoming', 'document.batch.integration']

    def _get_batch_creation_data(self, line):
        """Підготовка даних для створення партії"""
        return {
            'nomenclature_id': line.nomenclature_id.id,
            'quantity': line.qty,
            'receipt_doc': {
                'document_reference': self.number,
                'recorder_type': 'stock.receipt.incoming',
                'recorder_id': self.id,
                'period': self.posting_datetime or fields.Datetime.now(),
            },
            'location_dims': {
                'warehouse_id': self.warehouse_id.id,
                'location_id': self.warehouse_id.lot_stock_id.id,
            },
            'serial_numbers': self._get_line_serial_numbers(line),
        }

    def _get_line_serial_numbers(self, line):
        """Отримує серійні номери для позиції"""
        if hasattr(line, 'serial_numbers_text') and line.serial_numbers_text:
            return [s.strip() for s in line.serial_numbers_text.replace(',', '\n').split('\n') if s.strip()]
        return None


class StockReceiptDisposalBatchIntegration(models.Model):
    """Інтеграція накладних списання з віртуальними партіями"""
    _name = 'stock.receipt.disposal'
    _inherit = ['stock.receipt.disposal', 'document.batch.integration']

    def get_fifo_batches_for_disposal(self, line):
        """Отримує партії для списання за FIFO логікою"""
        batch_virtual_model = self.env['stock.batch.virtual']
        
        fifo_batches, remaining = batch_virtual_model.get_fifo_batches(
            nomenclature_id=line.nomenclature_id.id,
            location_id=self.warehouse_id.lot_stock_id.id,
            qty_needed=line.qty,
            company_id=self.company_id.id
        )
        
        if remaining > 0:
            raise ValidationError(
                _('Недостатньо залишку для списання номенклатури "%s". Потрібно: %s, доступно: %s') %
                (line.nomenclature_id.name, line.qty, line.qty - remaining)
            )
        
        return fifo_batches


class StockTransferBatchIntegration(models.Model):
    """Інтеграція переміщень з віртуальними партіями"""
    _name = 'stock.transfer'
    _inherit = ['stock.transfer', 'document.batch.integration']

    def get_transfer_batches(self, line):
        """Отримує партії для переміщення"""
        batch_virtual_model = self.env['stock.batch.virtual']
        
        # Використовуємо FIFO для вибору партій на переміщення
        fifo_batches, remaining = batch_virtual_model.get_fifo_batches(
            nomenclature_id=line.nomenclature_id.id,
            location_id=self.from_warehouse_id.lot_stock_id.id,
            qty_needed=line.qty,
            company_id=self.company_id.id
        )
        
        if remaining > 0:
            raise ValidationError(
                _('Недостатньо залишку для переміщення номенклатури "%s". Потрібно: %s, доступно: %s') %
                (line.nomenclature_id.name, line.qty, line.qty - remaining)
            )
        
        return fifo_batches

    @api.depends('number', 'state')
    def _compute_batch_ids(self):
        """Для переміщень показуємо партії що беруть участь в операції"""
        for record in self:
            if record.number and record.state == 'posted':
                # Шукаємо записи регістра для цього переміщення
                register_records = record.env['stock.balance.register'].search([
                    ('document_reference', 'like', record.number),
                    ('recorder_type', '=', 'stock.transfer'),
                    ('active', '=', True),
                ])
                
                # Отримуємо унікальні партії
                batch_numbers = list(set([r.batch_number for r in register_records if r.batch_number]))
                
                # Шукаємо віртуальні партії
                batches = record.env['stock.batch.virtual'].search([
                    ('batch_number', 'in', batch_numbers),
                ])
                
                record.batch_ids = batches
                record.batch_count = len(batches)
            else:
                super()._compute_batch_ids()