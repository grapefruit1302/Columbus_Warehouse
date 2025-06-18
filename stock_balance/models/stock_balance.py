import logging
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime, date
from collections import defaultdict

_logger = logging.getLogger(__name__)

class StockBalance(models.Model):
    _name = 'stock.balance'
    _description = 'Залишки товарів на складах'
    _rec_name = 'display_name'

    # Параметри звіту
    date_from = fields.Date('Дата з', required=True, default=fields.Date.today)
    date_to = fields.Date('Дата по', required=True, default=fields.Date.today)
    
    company_ids = fields.Many2many('res.company', 'stock_balance_company_rel', 
                                   'balance_id', 'company_id', 'Компанії')
    warehouse_ids = fields.Many2many('stock.warehouse', 'stock_balance_warehouse_rel',
                                     'balance_id', 'warehouse_id', 'Склади')
    category_ids = fields.Many2many('product.category', 'stock_balance_category_rel',
                                    'balance_id', 'category_id', 'Категорії товарів')
    
    report_type = fields.Selection([
        ('product_balance', 'Залишки товарів'),
    ], 'Вид звіту', default='product_balance', required=True)
    
    include_serial_numbers = fields.Boolean('Включити серійні номери', default=False)
    include_batch_details = fields.Boolean('Включити деталі партій', default=True)
    
    # Результати звіту
    line_ids = fields.One2many('stock.balance.line', 'balance_id', 'Рядки звіту')
    line_count = fields.Integer('Кількість рядків', compute='_compute_line_count')
    total_amount_no_vat = fields.Float('Загальна сума без ПДВ', compute='_compute_totals', digits='Product Price')
    total_amount_with_vat = fields.Float('Загальна сума з ПДВ', compute='_compute_totals', digits='Product Price')
    
    # Службові поля
    state = fields.Selection([
        ('draft', 'Параметри'),
        ('generated', 'Згенеровано'),
    ], 'Статус', default='draft')
    
    display_name = fields.Char('Назва', compute='_compute_display_name', store=True)
    
    @api.depends('report_type', 'date_to')
    def _compute_display_name(self):
        for record in self:
            if record.report_type == 'product_balance':
                record.display_name = f'Залишки товарів на {record.date_to}'
            else:
                record.display_name = f'Звіт на {record.date_to}'
    
    @api.depends('line_ids')
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids.filtered(lambda l: not l.is_batch_line and not l.is_serial_line))
    
    @api.depends('line_ids.amount_no_vat', 'line_ids.amount_with_vat')
    def _compute_totals(self):
        for record in self:
            # Підсумовуємо тільки основні рядки (не партії і не серійні номери)
            main_lines = record.line_ids.filtered(lambda l: not l.is_batch_line and not l.is_serial_line)
            record.total_amount_no_vat = sum(main_lines.mapped('amount_no_vat'))
            record.total_amount_with_vat = sum(main_lines.mapped('amount_with_vat'))
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        
        # Встановлюємо поточну компанію за замовчуванням
        if 'company_ids' in fields_list:
            res['company_ids'] = [(6, 0, [self.env.company.id])]
            
        return res
    
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from > record.date_to:
                raise UserError('Дата "з" не може бути більшою за дату "по"!')
    
    def action_generate_report(self):
        """Генерує звіт по залишках"""
        self.ensure_one()
        
        if not self.company_ids:
            raise UserError('Оберіть хоча б одну компанію!')
        
        # Очищаємо попередні результати
        self.line_ids.unlink()
        
        # Збираємо дані для звіту
        report_data = self._collect_balance_data()
        
        # Створюємо рядки звіту
        self._create_report_lines(report_data)
        
        # Змінюємо статус
        self.state = 'generated'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
    def _collect_balance_data(self):
        """Збирає дані по залишках товарів"""
        
        # Формуємо домени для фільтрації
        batch_domain = [
            ('date_received', '<=', self.date_to),
            ('quantity_available', '>', 0),
            ('state', '!=', 'depleted')
        ]
        
        if self.company_ids:
            batch_domain.append(('company_id', 'in', self.company_ids.ids))
            
        if self.warehouse_ids:
            batch_domain.append(('warehouse_id', 'in', self.warehouse_ids.ids))
            
        if self.category_ids:
            batch_domain.append(('nomenclature_id.categ_id', 'in', self.category_ids.ids))
        
        # Отримуємо партії товарів
        batches = self.env['product.batch'].search(batch_domain, order='date_received asc')
        
        # Групуємо дані по номенклатурі, складу, компанії
        balance_data = defaultdict(lambda: {
            'quantity': 0.0,
            'batches': [],
            'serials': [],
            'nomenclature_id': False,
            'warehouse_id': False,
            'company_id': False,
            'avg_price_no_vat': 0.0,
            'avg_price_with_vat': 0.0,
        })
        
        for batch in batches:
            key = (batch.nomenclature_id.id, batch.warehouse_id.id, batch.company_id.id)
            
            balance_data[key]['quantity'] += batch.quantity_available
            balance_data[key]['batches'].append({
                'batch_name': batch.name,
                'quantity': batch.quantity_available,
                'date_received': batch.date_received,
                'price_no_vat': batch.purchase_price_no_vat,
                'price_with_vat': batch.purchase_price_with_vat,
            })
            balance_data[key]['nomenclature_id'] = batch.nomenclature_id
            balance_data[key]['warehouse_id'] = batch.warehouse_id
            balance_data[key]['company_id'] = batch.company_id
            
            # Додаємо серійні номери якщо потрібно
            if self.include_serial_numbers and batch.serial_numbers:
                for serial in batch.serial_numbers:
                    if serial.is_available:
                        balance_data[key]['serials'].append({
                            'serial_number': serial.serial_number,
                            'batch_name': batch.name,
                        })
        
        # Обчислюємо середню ціну (FIFO)
        for key, data in balance_data.items():
            if data['batches']:
                # Сортуємо партії по даті (FIFO)
                data['batches'].sort(key=lambda x: x['date_received'])
                
                # Беремо ціну з найранішої партії
                data['avg_price_no_vat'] = data['batches'][0]['price_no_vat']
                data['avg_price_with_vat'] = data['batches'][0]['price_with_vat']
        
        return balance_data
    
    def _create_report_lines(self, balance_data):
        """Створює рядки звіту"""
        
        line_vals = []
        sequence = 1
        
        for key, data in balance_data.items():
            if data['quantity'] <= 0:
                continue
            
            # Основний рядок товару
            amount_no_vat = data['quantity'] * data['avg_price_no_vat']
            amount_with_vat = data['quantity'] * data['avg_price_with_vat']
            
            line_vals.append({
                'balance_id': self.id,
                'sequence': sequence,
                'nomenclature_id': data['nomenclature_id'].id,
                'warehouse_id': data['warehouse_id'].id,
                'company_id': data['company_id'].id,
                'quantity': data['quantity'],
                'uom_id': data['nomenclature_id'].base_uom_id.id,
                'price_no_vat': data['avg_price_no_vat'],
                'price_with_vat': data['avg_price_with_vat'],
                'amount_no_vat': amount_no_vat,
                'amount_with_vat': amount_with_vat,
            })
            sequence += 1
            
            # Рядки партій якщо потрібно
            if self.include_batch_details:
                for batch_info in data['batches']:
                    batch_amount_no_vat = batch_info['quantity'] * batch_info['price_no_vat']
                    batch_amount_with_vat = batch_info['quantity'] * batch_info['price_with_vat']
                    
                    line_vals.append({
                        'balance_id': self.id,
                        'sequence': sequence,
                        'nomenclature_id': data['nomenclature_id'].id,
                        'warehouse_id': data['warehouse_id'].id,
                        'company_id': data['company_id'].id,
                        'batch_name': batch_info['batch_name'],
                        'quantity': batch_info['quantity'],
                        'uom_id': data['nomenclature_id'].base_uom_id.id,
                        'date_received': batch_info['date_received'],
                        'price_no_vat': batch_info['price_no_vat'],
                        'price_with_vat': batch_info['price_with_vat'],
                        'amount_no_vat': batch_amount_no_vat,
                        'amount_with_vat': batch_amount_with_vat,
                        'is_batch_line': True,
                    })
                    sequence += 1
            
            # Рядки серійних номерів якщо потрібно
            if self.include_serial_numbers:
                for serial_info in data['serials']:
                    line_vals.append({
                        'balance_id': self.id,
                        'sequence': sequence,
                        'nomenclature_id': data['nomenclature_id'].id,
                        'warehouse_id': data['warehouse_id'].id,
                        'company_id': data['company_id'].id,
                        'batch_name': serial_info['batch_name'],
                        'serial_number': serial_info['serial_number'],
                        'quantity': 1.0,
                        'uom_id': data['nomenclature_id'].base_uom_id.id,
                        'price_no_vat': data['avg_price_no_vat'],
                        'price_with_vat': data['avg_price_with_vat'],
                        'amount_no_vat': data['avg_price_no_vat'],
                        'amount_with_vat': data['avg_price_with_vat'],
                        'is_serial_line': True,
                    })
                    sequence += 1
        
        # Створюємо всі рядки одним запитом
        if line_vals:
            self.env['stock.balance.line'].create(line_vals)
    
    def action_print_report(self):
        """Друкує звіт"""
        self.ensure_one()
        
        if self.state != 'generated':
            raise UserError('Спочатку згенеруйте звіт!')
        
        return {
            'type': 'ir.actions.report',
            'report_name': 'stock_balance.report_stock_balance_template',
            'report_type': 'qweb-pdf',
            'name': f'Залишки на складах - {self.display_name}',
            'context': {'active_ids': [self.id]},
            'data': {'balance_id': self.id}
        }
    
    def action_reset_to_draft(self):
        """Повертає до параметрів"""
        self.ensure_one()
        self.line_ids.unlink()
        self.state = 'draft'

class StockBalanceLine(models.Model):
    _name = 'stock.balance.line'
    _description = 'Рядок звіту по залишках'
    _order = 'sequence, id'

    balance_id = fields.Many2one('stock.balance', 'Звіт', required=True, ondelete='cascade')
    sequence = fields.Integer('Послідовність', default=1)
    
    nomenclature_id = fields.Many2one('product.nomenclature', 'Номенклатура')
    product_name = fields.Char('Назва товару', related='nomenclature_id.name', readonly=True)
    product_code = fields.Char('Код товару', related='nomenclature_id.code', readonly=True)
    
    warehouse_id = fields.Many2one('stock.warehouse', 'Склад')
    warehouse_name = fields.Char('Назва складу', related='warehouse_id.name', readonly=True)
    
    company_id = fields.Many2one('res.company', 'Компанія')
    company_name = fields.Char('Назва компанії', related='company_id.name', readonly=True)
    
    quantity = fields.Float('Кількість', digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', 'Од. виміру')
    uom_name = fields.Char('Од. виміру', related='uom_id.name', readonly=True)
    
    # Ціни та суми
    price_no_vat = fields.Float('Ціна без ПДВ', digits='Product Price')
    price_with_vat = fields.Float('Ціна з ПДВ', digits='Product Price')
    amount_no_vat = fields.Float('Сума без ПДВ', digits='Product Price')
    amount_with_vat = fields.Float('Сума з ПДВ', digits='Product Price')
    
    # Для партійних рядків
    batch_name = fields.Char('Номер партії')
    date_received = fields.Date('Дата надходження')
    
    # Для серійних номерів
    serial_number = fields.Char('Серійний номер')
    
    # Типи рядків
    is_batch_line = fields.Boolean('Рядок партії')
    is_serial_line = fields.Boolean('Рядок серійного номера')
    
    def name_get(self):
        result = []
        for record in self:
            if record.is_serial_line:
                name = f"{record.product_name} - S/N: {record.serial_number}"
            elif record.is_batch_line:
                name = f"{record.product_name} - Партія: {record.batch_name}"
            else:
                name = f"{record.product_name} - {record.warehouse_name}"
            result.append((record.id, name))
        return result