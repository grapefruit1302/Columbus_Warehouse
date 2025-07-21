from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class StockBalanceSheetWizard(models.TransientModel):
    """Wizard для формування оборотно-сальдової відомості"""
    _name = 'stock.balance.sheet.wizard'
    _description = 'Оборотно-сальдова відомість'

    date_from = fields.Date(
        'Дата з',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1)
    )
    
    date_to = fields.Date(
        'Дата до',
        required=True,
        default=fields.Date.today
    )
    
    nomenclature_ids = fields.Many2many(
        'product.nomenclature',
        'balance_sheet_nomenclature_rel',
        'wizard_id',
        'nomenclature_id',
        'Номенклатура'
    )
    
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        'balance_sheet_warehouse_rel',
        'wizard_id',
        'warehouse_id',
        'Склади'
    )
    
    company_id = fields.Many2one(
        'res.company',
        'Компанія',
        required=True,
        default=lambda self: self.env.company
    )
    
    include_zero_balances = fields.Boolean(
        'Включити нульові залишки',
        default=False
    )
    
    group_by = fields.Selection([
        ('nomenclature', 'За номенклатурою'),
        ('warehouse', 'За складами'),
        ('batch', 'За партіями'),
        ('nomenclature_warehouse', 'За номенклатурою та складами'),
        ('nomenclature_batch', 'За номенклатурою та партіями'),
    ], 'Групування', default='nomenclature_warehouse', required=True)

    def generate_report(self):
        """Генерує оборотно-сальдову відомість"""
        register_model = self.env['stock.balance.register']
        
        # Формуємо домен для вибірки
        domain = [
            ('period', '>=', fields.Datetime.combine(self.date_from, fields.datetime.min.time())),
            ('period', '<=', fields.Datetime.combine(self.date_to, fields.datetime.max.time())),
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
        ]
        
        if self.nomenclature_ids:
            domain.append(('nomenclature_id', 'in', self.nomenclature_ids.ids))
            
        if self.warehouse_ids:
            domain.append(('warehouse_id', 'in', self.warehouse_ids.ids))
        
        # Отримуємо дані з регістра
        records = register_model.search(domain)
        
        # Групуємо дані згідно налаштувань
        grouped_data = self._group_records(records)
        
        # Створюємо тимчасові записи звіту
        report_lines = []
        for group_key, group_records in grouped_data.items():
            line_data = self._calculate_line_data(group_key, group_records)
            
            if not self.include_zero_balances and line_data['balance_end'] == 0:
                continue
                
            report_lines.append(line_data)
        
        # Створюємо записи звіту
        report_ids = []
        for line_data in report_lines:
            report_line = self.env['stock.balance.sheet.line'].create(line_data)
            report_ids.append(report_line.id)
        
        # Відкриваємо звіт
        return {
            'name': _('Оборотно-сальдова відомість'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.balance.sheet.line',
            'view_mode': 'tree',
            'domain': [('id', 'in', report_ids)],
            'context': {
                'search_default_group_nomenclature': 1 if 'nomenclature' in self.group_by else 0,
                'search_default_group_warehouse': 1 if 'warehouse' in self.group_by else 0,
                'search_default_group_batch': 1 if 'batch' in self.group_by else 0,
            },
            'target': 'current',
        }

    def _group_records(self, records):
        """Групує записи згідно налаштувань"""
        grouped = {}
        
        for record in records:
            if self.group_by == 'nomenclature':
                key = ('nomenclature', record.nomenclature_id.id, record.nomenclature_id.name, '', '', '', '')
            elif self.group_by == 'warehouse':
                key = ('warehouse', record.warehouse_id.id if record.warehouse_id else 0, 
                      record.warehouse_id.name if record.warehouse_id else 'Без складу', '', '', '', '')
            elif self.group_by == 'batch':
                key = ('batch', 0, record.batch_number or 'Без партії', '', '', '', '')
            elif self.group_by == 'nomenclature_warehouse':
                key = ('nomenclature_warehouse', record.nomenclature_id.id, record.nomenclature_id.name,
                      record.warehouse_id.id if record.warehouse_id else 0,
                      record.warehouse_id.name if record.warehouse_id else 'Без складу', '', '')
            elif self.group_by == 'nomenclature_batch':
                key = ('nomenclature_batch', record.nomenclature_id.id, record.nomenclature_id.name,
                      0, record.batch_number or 'Без партії', '', '')
                      
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(record)
        
        return grouped

    def _calculate_line_data(self, group_key, records):
        """Обчислює дані для рядка звіту"""
        receipt_total = sum(rec.quantity for rec in records if rec.quantity > 0)
        disposal_total = sum(abs(rec.quantity) for rec in records if rec.quantity < 0)
        balance_end = sum(rec.quantity for rec in records)
        
        # Обчислюємо початковий залишок
        balance_start = self._get_balance_start(group_key, records)
        
        return {
            'group_type': group_key[0],
            'nomenclature_id': group_key[1] if group_key[1] and 'nomenclature' in group_key[0] else False,
            'nomenclature_name': group_key[2] if 'nomenclature' in group_key[0] else '',
            'warehouse_id': group_key[3] if len(group_key) > 3 and group_key[3] else False,
            'warehouse_name': group_key[4] if len(group_key) > 4 else '',
            'batch_number': group_key[5] if len(group_key) > 5 else '',
            'balance_start': balance_start,
            'receipt_total': receipt_total,
            'disposal_total': disposal_total,
            'balance_end': balance_end,
            'uom_name': records[0].uom_id.name if records else '',
        }

    def _get_balance_start(self, group_key, records):
        """Обчислює початковий залишок на дату початку періоду"""
        register_model = self.env['stock.balance.register']
        
        # Формуємо домен для початкового залишку
        domain = [
            ('period', '<', fields.Datetime.combine(self.date_from, fields.datetime.min.time())),
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
        ]
        
        if 'nomenclature' in group_key[0] and group_key[1]:
            domain.append(('nomenclature_id', '=', group_key[1]))
            
        if 'warehouse' in group_key[0] and len(group_key) > 3 and group_key[3]:
            domain.append(('warehouse_id', '=', group_key[3]))
            
        if 'batch' in group_key[0] and len(group_key) > 5 and group_key[5]:
            domain.append(('batch_number', '=', group_key[5]))
        
        start_records = register_model.search(domain)
        return sum(rec.quantity for rec in start_records)


class StockBalanceSheetLine(models.TransientModel):
    """Рядок оборотно-сальдової відомості"""
    _name = 'stock.balance.sheet.line'
    _description = 'Рядок оборотно-сальдової відомості'

    group_type = fields.Char('Тип групування')
    nomenclature_id = fields.Many2one('product.nomenclature', 'Номенклатура')
    nomenclature_name = fields.Char('Назва номенклатури')
    warehouse_id = fields.Many2one('stock.warehouse', 'Склад')
    warehouse_name = fields.Char('Назва складу')
    batch_number = fields.Char('Партія')
    
    balance_start = fields.Float('Початковий залишок', digits='Product Unit of Measure')
    receipt_total = fields.Float('Надходження', digits='Product Unit of Measure')
    disposal_total = fields.Float('Списання', digits='Product Unit of Measure')
    balance_end = fields.Float('Кінцевий залишок', digits='Product Unit of Measure')
    
    uom_name = fields.Char('Од. виміру')


class StockBatchMovementWizard(models.TransientModel):
    """Wizard для звіту по руху партій"""
    _name = 'stock.batch.movement.wizard'
    _description = 'Рух партій'

    date_from = fields.Date('Дата з', required=True, default=fields.Date.today)
    date_to = fields.Date('Дата до', required=True, default=fields.Date.today)
    
    nomenclature_ids = fields.Many2many(
        'product.nomenclature',
        'batch_movement_nomenclature_rel',
        'wizard_id',
        'nomenclature_id',
        'Номенклатура'
    )
    
    batch_numbers = fields.Text('Номери партій (через кому)')
    
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        'batch_movement_warehouse_rel',
        'wizard_id',
        'warehouse_id',
        'Склади'
    )
    
    company_id = fields.Many2one(
        'res.company',
        'Компанія',
        required=True,
        default=lambda self: self.env.company
    )

    def generate_report(self):
        """Генерує звіт по руху партій"""
        register_model = self.env['stock.balance.register']
        
        domain = [
            ('period', '>=', fields.Datetime.combine(self.date_from, fields.datetime.min.time())),
            ('period', '<=', fields.Datetime.combine(self.date_to, fields.datetime.max.time())),
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
            ('batch_number', '!=', False),
        ]
        
        if self.nomenclature_ids:
            domain.append(('nomenclature_id', 'in', self.nomenclature_ids.ids))
            
        if self.warehouse_ids:
            domain.append(('warehouse_id', 'in', self.warehouse_ids.ids))
            
        if self.batch_numbers:
            batch_list = [b.strip() for b in self.batch_numbers.split(',') if b.strip()]
            if batch_list:
                domain.append(('batch_number', 'in', batch_list))
        
        return {
            'name': _('Рух партій'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.balance.register',
            'view_mode': 'tree',
            'domain': domain,
            'context': {
                'search_default_group_batch': 1,
                'search_default_group_nomenclature': 1,
            },
            'target': 'current',
        }

    def generate_batch_analysis(self):
        """Генерує аналіз партій через віртуальну модель"""
        domain = []
        
        if self.nomenclature_ids:
            domain.append(('nomenclature_id', 'in', self.nomenclature_ids.ids))
            
        if self.warehouse_ids:
            domain.append(('warehouse_id', 'in', self.warehouse_ids.ids))
            
        if self.batch_numbers:
            batch_list = [b.strip() for b in self.batch_numbers.split(',') if b.strip()]
            if batch_list:
                domain.append(('batch_number', 'in', batch_list))
        
        return {
            'name': _('Аналіз партій'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.batch.virtual',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {
                'search_default_active': 1,
                'search_default_group_nomenclature': 1,
            },
            'target': 'current',
        }