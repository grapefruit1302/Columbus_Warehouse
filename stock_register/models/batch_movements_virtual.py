from odoo import models, fields, api, tools, _
import logging

_logger = logging.getLogger(__name__)

class BatchMovementVirtual(models.Model):
    """Віртуальний перегляд рухів партій з регістра накопичення"""
    _name = 'batch.movement.virtual'
    _description = 'Рухи партій'
    _auto = False
    _order = 'movement_date desc, id desc'

    # Поля для відображення рухів партій
    batch_number = fields.Char('Номер партії')
    nomenclature_id = fields.Many2one('product.nomenclature', 'Номенклатура')
    warehouse_id = fields.Many2one('stock.warehouse', 'Склад')
    location_id = fields.Many2one('stock.location', 'Локація')
    quantity = fields.Float('Кількість', digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', 'Од. виміру')
    
    movement_type = fields.Selection([
        ('in', 'Надходження'),
        ('out', 'Списання'),
        ('transfer', 'Переміщення'),
    ], 'Тип руху', compute='_compute_movement_type')
    
    operation_type = fields.Selection([
        ('receipt', 'Надходження'),
        ('disposal', 'Списання'),
        ('transfer', 'Переміщення'),
        ('inventory', 'Інвентаризація'),
        ('adjustment', 'Коригування'),
        ('return', 'Повернення'),
    ], 'Операція')
    
    document_reference = fields.Char('Документ')
    movement_date = fields.Datetime('Дата руху')
    company_id = fields.Many2one('res.company', 'Компанія')
    notes = fields.Text('Примітки')
    
    # Додаткові поля для аналізу
    running_balance = fields.Float('Залишок після операції', digits='Product Unit of Measure')
    recorder_type = fields.Char('Тип документа')

    def init(self):
        """Створює SQL VIEW для рухів партій"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT 
                    sbr.id,
                    sbr.batch_number,
                    sbr.nomenclature_id,
                    sbr.warehouse_id,
                    sbr.location_id,
                    sbr.quantity,
                    sbr.uom_id,
                    sbr.operation_type,
                    sbr.document_reference,
                    sbr.period as movement_date,
                    sbr.company_id,
                    sbr.notes,
                    sbr.recorder_type,
                    -- Обчислюємо накопичуючий залишок
                    SUM(sbr2.quantity) OVER (
                        PARTITION BY sbr.batch_number, sbr.nomenclature_id, sbr.warehouse_id
                        ORDER BY sbr2.period, sbr2.id
                        ROWS UNBOUNDED PRECEDING
                    ) as running_balance
                FROM stock_balance_register sbr
                JOIN stock_balance_register sbr2 ON (
                    sbr2.batch_number = sbr.batch_number 
                    AND sbr2.nomenclature_id = sbr.nomenclature_id
                    AND COALESCE(sbr2.warehouse_id, 0) = COALESCE(sbr.warehouse_id, 0)
                    AND sbr2.period <= sbr.period
                    AND sbr2.active = true
                )
                WHERE sbr.active = true 
                    AND sbr.batch_number IS NOT NULL 
                    AND sbr.batch_number != ''
                ORDER BY sbr.period DESC, sbr.id DESC
            )
        """)

    @api.depends('quantity')
    def _compute_movement_type(self):
        """Визначає тип руху на основі кількості"""
        for record in self:
            if record.quantity > 0:
                record.movement_type = 'in'
            elif record.quantity < 0:
                record.movement_type = 'out'
            else:
                record.movement_type = 'transfer'

    def action_view_batch(self):
        """Відкриває партію до якої відноситься рух"""
        self.ensure_one()
        return {
            'name': _('Партія %s') % self.batch_number,
            'type': 'ir.actions.act_window',
            'res_model': 'stock.batch.virtual',
            'view_mode': 'form',
            'domain': [
                ('batch_number', '=', self.batch_number),
                ('nomenclature_id', '=', self.nomenclature_id.id),
                ('warehouse_id', '=', self.warehouse_id.id if self.warehouse_id else False),
            ],
            'context': {},
        }

    def action_view_document(self):
        """Відкриває документ-джерело руху"""
        self.ensure_one()
        
        if not self.recorder_type or not self.document_reference:
            raise UserError(_('Немає інформації про документ-джерело'))
        
        # Мапимо типи документів
        model_mapping = {
            'stock.receipt.incoming': 'stock.receipt.incoming',
            'stock.receipt.disposal': 'stock.receipt.disposal', 
            'stock.transfer': 'stock.transfer',
            'legacy.batch.creation': None,
            'legacy.consumption': None,
        }
        
        target_model = model_mapping.get(self.recorder_type)
        if not target_model:
            raise UserError(_('Тип документа "%s" не підтримується для перегляду') % self.recorder_type)
        
        # Шукаємо документ за номером
        document = self.env[target_model].search([
            ('number', '=', self.document_reference)
        ], limit=1)
        
        if not document:
            raise UserError(_('Документ "%s" не знайдено') % self.document_reference)
        
        return {
            'name': _('Документ %s') % self.document_reference,
            'type': 'ir.actions.act_window',
            'res_model': target_model,
            'res_id': document.id,
            'view_mode': 'form',
            'target': 'current',
        }