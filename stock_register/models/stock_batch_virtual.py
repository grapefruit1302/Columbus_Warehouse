from odoo import models, fields, api, tools, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class StockBatchVirtual(models.Model):
    """Віртуальний перегляд партій з регістра накопичення (замість stock.batch)"""
    _name = 'stock.batch.virtual'
    _description = 'Партії товарів'
    _auto = False
    _rec_name = 'batch_number'

    # Поля як в старій моделі stock.batch
    batch_number = fields.Char('Номер партії')
    nomenclature_id = fields.Many2one('product.nomenclature', 'Номенклатура')
    warehouse_id = fields.Many2one('stock.warehouse', 'Склад')  
    location_id = fields.Many2one('stock.location', 'Локація')
    current_qty = fields.Float('Поточна кількість', digits='Product Unit of Measure')
    available_qty = fields.Float('Доступна кількість', digits='Product Unit of Measure')
    initial_qty = fields.Float('Початкова кількість', digits='Product Unit of Measure')
    date_created = fields.Datetime('Дата створення')
    source_document_number = fields.Char('Номер документу')
    source_document_type = fields.Char('Тип документу')
    state = fields.Selection([
        ('active', 'Активна'),
        ('depleted', 'Вичерпана'),
    ], 'Статус')
    company_id = fields.Many2one('res.company', 'Компанія')
    uom_id = fields.Many2one('uom.uom', 'Одиниця виміру')

    def init(self):
        """Створює SQL VIEW для віртуальної моделі партій"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT 
                    ROW_NUMBER() OVER (ORDER BY batch_number, nomenclature_id, warehouse_id) as id,
                    batch_number,
                    nomenclature_id,
                    warehouse_id,
                    MAX(location_id) as location_id,
                    SUM(quantity) as current_qty,
                    SUM(quantity) as available_qty,
                    SUM(CASE WHEN quantity > 0 THEN quantity ELSE 0 END) as initial_qty,
                    MIN(period) as date_created,
                    MAX(document_reference) as source_document_number,
                    MAX(recorder_type) as source_document_type,
                    CASE 
                        WHEN SUM(quantity) <= 0 THEN 'depleted'
                        ELSE 'active'
                    END as state,
                    company_id,
                    MAX(uom_id) as uom_id
                FROM stock_balance_register 
                WHERE active = true 
                    AND batch_number IS NOT NULL 
                    AND batch_number != ''
                GROUP BY batch_number, nomenclature_id, warehouse_id, company_id
                HAVING SUM(quantity) != 0
                ORDER BY batch_number, nomenclature_id
            )
        """)

    def action_view_movements(self):
        """Показати рухи партії з регістра накопичення"""
        self.ensure_one()
        return {
            'name': _('Рухи партії %s') % self.batch_number,
            'type': 'ir.actions.act_window',
            'res_model': 'stock.balance.register',
            'view_mode': 'list,form',
            'domain': [
                ('batch_number', '=', self.batch_number),
                ('nomenclature_id', '=', self.nomenclature_id.id),
                ('active', '=', True)
            ],
            'context': {
                'search_default_group_by_period': 1,
                'create': False,
            },
        }

    @api.model
    def get_fifo_batches(self, nomenclature_id, location_id, qty_needed, company_id=None):
        """
        FIFO логіка через регістр накопичення (backward compatibility)
        
        Args:
            nomenclature_id (int): ID номенклатури
            location_id (int): ID локації
            qty_needed (float): потрібна кількість
            company_id (int): ID компанії
            
        Returns:
            tuple: (список партій, залишок що не вистачає)
        """
        if company_id is None:
            company_id = self.env.company.id

        # Отримуємо склад з локації
        location = self.env['stock.location'].browse(location_id)
        warehouse_id = location.warehouse_id.id if location.warehouse_id else None

        # Використовуємо регістр накопичення для FIFO
        register_model = self.env['stock.balance.register']
        location_dimensions = {}
        if warehouse_id:
            location_dimensions['warehouse_id'] = warehouse_id

        try:
            fifo_batches = register_model.fifo_consumption(
                nomenclature_id=nomenclature_id,
                quantity=qty_needed,
                location_dimensions=location_dimensions,
                company_id=company_id
            )

            # Конвертуємо в формат що очікує старий код
            result_batches = []
            for batch_info in fifo_batches:
                # Створюємо віртуальний об'єкт партії
                batch_virtual = self.new({
                    'batch_number': batch_info['batch_number'],
                    'nomenclature_id': nomenclature_id,
                    'warehouse_id': warehouse_id,
                    'location_id': location_id,
                    'current_qty': batch_info['balance'],
                    'available_qty': batch_info['balance'],
                    'company_id': company_id,
                    'state': 'active'
                })

                result_batches.append({
                    'batch': batch_virtual,
                    'qty': batch_info['quantity'],
                })

            return result_batches, 0.0

        except ValidationError:
            # Якщо недостатньо залишку
            return [], qty_needed

    def action_block_batch(self):
        """Заблокувати партію (деактивувати всі записи партії)"""
        self.ensure_one()
        register_records = self.env['stock.balance.register'].search([
            ('batch_number', '=', self.batch_number),
            ('nomenclature_id', '=', self.nomenclature_id.id),
            ('warehouse_id', '=', self.warehouse_id.id if self.warehouse_id else False),
            ('active', '=', True)
        ])
        
        if register_records:
            register_records.write({'active': False})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Партію заблоковано'),
                    'message': _('Партію %s заблоковано') % self.batch_number,
                    'type': 'success',
                }
            }

    def action_unblock_batch(self):
        """Розблокувати партію"""
        self.ensure_one()
        register_records = self.env['stock.balance.register'].search([
            ('batch_number', '=', self.batch_number),
            ('nomenclature_id', '=', self.nomenclature_id.id),
            ('warehouse_id', '=', self.warehouse_id.id if self.warehouse_id else False),
            ('active', '=', False)
        ])
        
        if register_records:
            register_records.write({'active': True})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Партію розблоковано'),
                    'message': _('Партію %s розблоковано') % self.batch_number,
                    'type': 'success',
                }
            }

    @api.model
    def create_batch_from_receipt(self, nomenclature_id, receipt_number, qty, uom_id,
                                  location_id, company_id, date_created=None, serial_numbers=None):
        """
        Backward compatibility: створення партії через регістр накопичення
        
        Returns:
            stock.batch.virtual: віртуальний об'єкт партії
        """
        register_model = self.env['stock.balance.register']
        
        location = self.env['stock.location'].browse(location_id)
        warehouse_id = location.warehouse_id.id if location.warehouse_id else None
        
        location_dims = {}
        if warehouse_id:
            location_dims['warehouse_id'] = warehouse_id
            location_dims['location_id'] = location_id

        receipt_doc = {
            'document_reference': receipt_number,
            'recorder_type': 'legacy.batch.creation',
            'recorder_id': 0,
            'period': date_created or fields.Datetime.now(),
        }

        # Створюємо партію через регістр
        batch_number = register_model.create_batch_from_receipt(
            nomenclature_id=nomenclature_id,
            quantity=qty,
            receipt_doc=receipt_doc,
            location_dims=location_dims,
            serial_numbers=serial_numbers.split(',') if serial_numbers else None
        )

        # Повертаємо віртуальний об'єкт партії
        return self.new({
            'batch_number': batch_number,
            'nomenclature_id': nomenclature_id,
            'warehouse_id': warehouse_id,
            'location_id': location_id,
            'current_qty': qty,
            'available_qty': qty,
            'initial_qty': qty,
            'date_created': date_created or fields.Datetime.now(),
            'source_document_number': receipt_number,
            'state': 'active',
            'company_id': company_id,
            'uom_id': uom_id,
        })

    def consume_qty(self, qty, operation_type='consumption', document_reference='', notes=''):
        """
        Backward compatibility: списання з партії через регістр
        """
        self.ensure_one()
        register_model = self.env['stock.balance.register']

        # Створюємо запис списання в регістрі
        dimensions = {
            'nomenclature_id': self.nomenclature_id.id,
            'batch_number': self.batch_number,
            'company_id': self.company_id.id,
        }

        if self.warehouse_id:
            dimensions['warehouse_id'] = self.warehouse_id.id
        if self.location_id:
            dimensions['location_id'] = self.location_id.id

        resources = {
            'quantity': -qty,  # Від'ємна для списання
            'uom_id': self.uom_id.id,
        }

        attributes = {
            'operation_type': operation_type,
            'document_reference': document_reference,
            'recorder_type': 'legacy.consumption',
            'recorder_id': 0,
            'period': fields.Datetime.now(),
            'notes': notes,
        }

        register_model.write_record(dimensions, resources, attributes)
        return True