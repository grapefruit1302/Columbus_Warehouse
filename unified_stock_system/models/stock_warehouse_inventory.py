from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)

class StockWarehouseInventory(models.Model):
    """Централізована модель складських залишків"""
    _name = 'stock.warehouse.inventory'
    _description = 'Складські залишки'
    _rec_name = 'display_name'
    _order = 'warehouse_id, nomenclature_id, batch_name'

    # Основні ідентифікатори
    warehouse_id = fields.Many2one(
        'stock.warehouse', 
        'Склад', 
        required=True
    )
    
    nomenclature_id = fields.Many2one(
        'product.nomenclature', 
        'Номенклатура', 
        required=True
    )
    
    batch_name = fields.Char(
        'Номер партії',
        help='Назва партії товару'
    )
    
    company_id = fields.Many2one(
        'res.company',
        'Компанія',
        required=True,
        default=lambda self: self.env.company
    )
    
    # Кількості
    qty_on_hand = fields.Float(
        'Кількість в наявності',
        digits='Product Unit of Measure',
        default=0.0
    )
    
    qty_available = fields.Float(
        'Доступно',
        compute='_compute_qty_available',
        store=True,
        digits='Product Unit of Measure'
    )
    
    uom_id = fields.Many2one(
        'uom.uom',
        'Одиниця виміру',
        required=True
    )
    
    # Вартісні показники
    unit_cost = fields.Float(
        'Собівартість за одиницю',
        digits='Product Price'
    )
    
    total_cost = fields.Float(
        'Загальна вартість',
        compute='_compute_total_cost',
        store=True,
        digits='Product Price'
    )
    
    # Метадані
    last_movement_date = fields.Datetime(
        'Дата останнього руху',
        default=fields.Datetime.now
    )
    
    source_document_type = fields.Selection([
        ('receipt_incoming', 'Прихідна накладна'),
        ('receipt_disposal', 'Акт оприходування'),
        ('receipt_return', 'Повернення з сервісу'),
        ('transfer', 'Переміщення'),
        ('adjustment', 'Корекція'),
        ('initial', 'Початковий залишок')
    ], 'Тип джерела')
    
    source_document_id = fields.Integer('ID документа джерела')
    source_document_number = fields.Char('Номер документа джерела')
    
    # Службові поля
    active = fields.Boolean('Активний', default=True)
    display_name = fields.Char('Назва', compute='_compute_display_name')
    
    # Серійні номери (якщо треба)
    serial_numbers = fields.Text('Серійні номери')
    
    @api.depends('qty_on_hand')
    def _compute_qty_available(self):
        for record in self:
            record.qty_available = record.qty_on_hand
    
    @api.depends('qty_on_hand', 'unit_cost')
    def _compute_total_cost(self):
        for record in self:
            record.total_cost = record.qty_on_hand * record.unit_cost
    
    @api.depends('warehouse_id', 'nomenclature_id', 'batch_name')
    def _compute_display_name(self):
        for record in self:
            parts = [record.nomenclature_id.name or '']
            if record.batch_name:
                parts.append(f"({record.batch_name})")
            parts.append(f"- {record.warehouse_id.name or ''}")
            record.display_name = ' '.join(parts)
    
    @api.model_create_multi
    def create(self, vals_list):
        """При створенні перевіряємо унікальність ключа"""
        for vals in vals_list:
            existing = self._find_existing_record(vals)
            if existing:
                # Якщо запис існує, оновлюємо його замість створення нового
                existing._update_quantities(vals)
                return existing
        return super().create(vals_list)
    
    def _find_existing_record(self, vals):
        """Знаходить існуючий запис за ключем"""
        domain = [
            ('warehouse_id', '=', vals.get('warehouse_id')),
            ('nomenclature_id', '=', vals.get('nomenclature_id')),
            ('company_id', '=', vals.get('company_id', self.env.company.id)),
        ]
        
        # Додаємо партію до пошуку
        batch_name = vals.get('batch_name')
        if batch_name:
            domain.append(('batch_name', '=', batch_name))
        else:
            domain.append(('batch_name', '=', False))
            
        return self.search(domain, limit=1)
    
    def _update_quantities(self, vals):
        """Оновлює кількості існуючого запису"""
        self.ensure_one()
        
        new_qty = vals.get('qty_on_hand', 0)
        if vals.get('operation_type') == 'add':
            self.qty_on_hand += new_qty
        elif vals.get('operation_type') == 'subtract':
            self.qty_on_hand -= new_qty
        elif vals.get('operation_type') == 'set':
            self.qty_on_hand = new_qty
        
        # Оновлюємо інші поля
        if 'unit_cost' in vals:
            self.unit_cost = vals['unit_cost']
        if 'last_movement_date' in vals:
            self.last_movement_date = vals['last_movement_date']
        if 'source_document_type' in vals:
            self.source_document_type = vals['source_document_type']
        if 'source_document_number' in vals:
            self.source_document_number = vals['source_document_number']
    
    @api.model
    def update_from_receipt_incoming(self, receipt_line):
        """Оновлює залишки з прихідної накладної"""
        vals = {
            'warehouse_id': receipt_line.receipt_id.warehouse_id.id,
            'nomenclature_id': receipt_line.nomenclature_id.id,
            'batch_name': receipt_line.batch_name,
            'company_id': receipt_line.receipt_id.company_id.id,
            'qty_on_hand': receipt_line.qty,
            'uom_id': receipt_line.selected_uom_id.id,
            'unit_cost': receipt_line.price_unit,
            'source_document_type': 'receipt_incoming',
            'source_document_number': receipt_line.receipt_id.number,
            'operation_type': 'add',
            'last_movement_date': receipt_line.receipt_id.posting_datetime,
        }
        
        return self.create([vals])
    
    @api.model
    def update_from_receipt_disposal(self, disposal_line):
        """Оновлює залишки з акта оприходування"""
        vals = {
            'warehouse_id': disposal_line.disposal_id.warehouse_id.id,
            'nomenclature_id': disposal_line.nomenclature_id.id,
            'batch_name': disposal_line.batch_name,
            'company_id': disposal_line.disposal_id.company_id.id,
            'qty_on_hand': disposal_line.qty,
            'uom_id': disposal_line.selected_uom_id.id,
            'unit_cost': disposal_line.price_unit if hasattr(disposal_line, 'price_unit') else 0,
            'source_document_type': 'receipt_disposal',
            'source_document_number': disposal_line.disposal_id.number,
            'operation_type': 'add',
            'last_movement_date': disposal_line.disposal_id.posting_datetime,
        }
        
        return self.create([vals])
    
    @api.model
    def update_from_receipt_return(self, return_line):
        """Оновлює залишки з повернення з сервісу"""
        vals = {
            'warehouse_id': return_line.return_id.warehouse_id.id,
            'nomenclature_id': return_line.nomenclature_id.id,
            'batch_name': return_line.batch_name,
            'company_id': return_line.return_id.company_id.id,
            'qty_on_hand': return_line.qty,
            'uom_id': return_line.selected_uom_id.id,
            'unit_cost': return_line.price_unit if hasattr(return_line, 'price_unit') else 0,
            'source_document_type': 'receipt_return',
            'source_document_number': return_line.return_id.number,
            'operation_type': 'add',
            'last_movement_date': return_line.return_id.posting_datetime,
            'serial_numbers': return_line.serial_numbers if hasattr(return_line, 'serial_numbers') else None,
        }
        
        return self.create([vals])
    
    @api.model
    def update_from_transfer(self, transfer_line, operation_type='subtract'):
        """Оновлює залишки з документа переміщення"""
        
        # Визначаємо склад та операцію
        if operation_type == 'subtract':
            # Списання з джерела
            if transfer_line.transfer_id.transfer_type in ['warehouse', 'warehouse_employee']:
                warehouse_id = transfer_line.transfer_id.warehouse_from_id.id
            else:
                # Для працівників поки що пропускаємо
                return False
        else:
            # Додавання в пункт призначення  
            if transfer_line.transfer_id.transfer_type in ['warehouse', 'employee_warehouse']:
                warehouse_id = transfer_line.transfer_id.warehouse_to_id.id
            else:
                # Для працівників поки що пропускаємо
                return False
        
        vals = {
            'warehouse_id': warehouse_id,
            'nomenclature_id': transfer_line.nomenclature_id.id,
            'batch_name': transfer_line.lot_batch,
            'company_id': transfer_line.transfer_id.company_id.id,
            'qty_on_hand': transfer_line.qty,
            'uom_id': transfer_line.selected_uom_id.id,
            'source_document_type': 'transfer',
            'source_document_number': transfer_line.transfer_id.number,
            'operation_type': operation_type,
            'last_movement_date': transfer_line.transfer_id.posting_datetime,
        }
        
        return self.create([vals])
    
    @api.model
    def get_available_stock_for_transfer(self, warehouse_id=None, employee_id=None, 
                                       company_id=None, nomenclature_id=None):
        """Повертає доступні залишки для переміщення"""
        
        domain = [('qty_on_hand', '>', 0), ('active', '=', True)]
        
        if warehouse_id:
            domain.append(('warehouse_id', '=', warehouse_id))
        if company_id:
            domain.append(('company_id', '=', company_id))
        if nomenclature_id:
            domain.append(('nomenclature_id', '=', nomenclature_id))
        
        # Для працівників додаємо окрему логіку пізніше
        
        return self.search(domain)
    
    @api.model
    def cleanup_zero_quantities(self):
        """Очищає записи з нульовими залишками"""
        zero_records = self.search([
            ('qty_on_hand', '<=', 0)
        ])
        zero_records.write({'active': False})
        
        return len(zero_records)


class StockWarehouseInventoryMigration(models.TransientModel):
    _name = 'stock.warehouse.inventory.migration'
    _description = 'Міграція існуючих залишків'
    
    def migrate_existing_data(self):
        """Мігрує існуючі дані в централізовану модель"""
        
        # Очищаємо існуючі записи
        self.env['stock.warehouse.inventory'].search([]).unlink()
        
        migrated_count = 0
        
        # Мігруємо з прихідних накладних
        receipts = self.env['stock.receipt.incoming'].search([('state', '=', 'posted')])
        for receipt in receipts:
            for line in receipt.line_ids:
                try:
                    self.env['stock.warehouse.inventory'].update_from_receipt_incoming(line)
                    migrated_count += 1
                except Exception as e:
                    _logger.warning(f"Помилка міграції прихідної накладної {receipt.number}: {e}")
        
        # Мігруємо з актів оприходування
        disposals = self.env['stock.receipt.disposal'].search([('state', '=', 'posted')])
        for disposal in disposals:
            for line in disposal.line_ids:
                try:
                    self.env['stock.warehouse.inventory'].update_from_receipt_disposal(line)
                    migrated_count += 1
                except Exception as e:
                    _logger.warning(f"Помилка міграції акта оприходування {disposal.number}: {e}")
        
        # Мігруємо з поверненнь з сервісу
        returns = self.env['stock.receipt.return'].search([('state', '=', 'posted')])
        for return_doc in returns:
            for line in return_doc.line_ids:
                try:
                    # Припускаємо аналогічний метод для поверненнь
                    self.env['stock.warehouse.inventory'].update_from_receipt_return(line)
                    migrated_count += 1
                except Exception as e:
                    _logger.warning(f"Помилка міграції повернення {return_doc.number}: {e}")
        
        # Очищаємо записи з нульовими залишками
        cleaned_count = self.env['stock.warehouse.inventory'].cleanup_zero_quantities()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Міграція завершена',
                'message': f'Мігровано {migrated_count} записів. Очищено {cleaned_count} нульових записів.',
                'type': 'success',
                'sticky': False,
            }
        }