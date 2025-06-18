from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta

class StockBatchReportWizard(models.TransientModel):
    _name = 'stock.batch.report.wizard'
    _description = 'Wizard для створення звітів по партіях'

    report_type = fields.Selection([
        ('movement', 'Звіт руху товарів'),
        ('balance', 'Звіт залишків товарів'),
    ], 'Тип звіту', required=True, default='balance')
    
    date_from = fields.Date(
        'Дата з', 
        required=True,
        default=lambda self: fields.Date.today().replace(day=1)
    )
    
    date_to = fields.Date(
        'Дата по', 
        required=True,
        default=fields.Date.today
    )
    
    company_id = fields.Many2one(
        'res.company', 
        'Компанія',
        required=True,
        default=lambda self: self.env.company
    )
    
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        'batch_report_warehouse_rel',
        'wizard_id',
        'warehouse_id',
        'Склади'
    )
    
    nomenclature_ids = fields.Many2many(
        'product.nomenclature',
        'batch_report_nomenclature_rel',
        'wizard_id',
        'nomenclature_id',
        'Номенклатура'
    )
    
    category_ids = fields.Many2many(
        'product.category',
        'batch_report_category_rel',
        'wizard_id',
        'category_id',
        'Категорії товарів'
    )
    
    detail_level = fields.Selection([
        ('warehouse', 'По складах'),
        ('nomenclature', 'По номенклатурі'),
        ('batch', 'По партіях'),
    ], 'Рівень деталізації', required=True, default='nomenclature')
    
    show_zero_qty = fields.Boolean(
        'Показувати нульові залишки',
        default=False,
        help='Включати в звіт товари з нульовою кількістю'
    )
    
    show_blocked = fields.Boolean(
        'Показувати заблоковані партії',
        default=False
    )
    
    group_by_state = fields.Boolean(
        'Групувати по статусу партії',
        default=False
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_('Дата початку не може бути пізніше дати закінчення!'))

    @api.onchange('warehouse_ids')
    def _onchange_warehouse_ids(self):
        """Очищаємо залежні поля при зміні складів"""
        pass

    def action_generate_report(self):
        """Генерує звіт відповідно до налаштувань"""
        self.ensure_one()
        
        if self.report_type == 'movement':
            return self._generate_movement_report()
        else:
            return self._generate_balance_report()

    def _generate_movement_report(self):
        """Генерує звіт руху товарів"""
        return {
            'type': 'ir.actions.report',
            'report_name': 'stock_batch_management.movement_report_template',
            'report_type': 'qweb-pdf',
            'context': self.env.context,
        }

    def _generate_balance_report(self):
        """Генерує звіт залишків товарів"""
        return {
            'type': 'ir.actions.report',
            'report_name': 'stock_batch_management.balance_report_template',
            'report_type': 'qweb-pdf',
            'context': self.env.context,
        }

    def _get_movement_domain(self):
        """Формує domain для пошуку рухів"""
        domain = [
            ('date', '>=', fields.Datetime.to_datetime(self.date_from)),
            ('date', '<=', fields.Datetime.to_datetime(self.date_to).replace(hour=23, minute=59, second=59)),
            ('company_id', '=', self.company_id.id),
        ]
        
        if self.warehouse_ids:
            # Отримуємо всі локації обраних складів
            warehouse_locations = []
            for warehouse in self.warehouse_ids:
                warehouse_locations.extend([
                    warehouse.lot_stock_id.id,
                    warehouse.wh_input_stock_loc_id.id,
                    warehouse.wh_output_stock_loc_id.id,
                ])
            
            domain.extend([
                '|',
                ('location_from_id', 'in', warehouse_locations),
                ('location_to_id', 'in', warehouse_locations)
            ])
        
        if self.nomenclature_ids:
            domain.append(('batch_id.nomenclature_id', 'in', self.nomenclature_ids.ids))
        
        if self.category_ids:
            domain.append(('batch_id.nomenclature_id.categ_id', 'in', self.category_ids.ids))
        
        if not self.show_blocked:
            domain.append(('batch_id.is_active', '=', True))
        
        return domain

    def _get_batch_domain(self):
        """Формує domain для пошуку партій"""
        import logging
        _logger = logging.getLogger(__name__)
        
        domain = []
        
        # Логіка компаній: якщо вибрана головна компанія, шукаємо у всіх дочірніх
        current_company = self.company_id
        parent_company = current_company.parent_id or current_company
        
        if current_company == parent_company:
            # Вибрана головна компанія - шукаємо у всіх дочірніх
            child_companies = self.env['res.company'].search([
                '|',
                ('id', '=', parent_company.id),
                ('parent_id', '=', parent_company.id)
            ])
            domain.append(('company_id', 'in', child_companies.ids))
        else:
            # Вибрана конкретна дочірня компанія
            domain.append(('company_id', '=', current_company.id))
        
        if self.warehouse_ids:
            # Отримуємо всі локації обраних складів
            warehouse_locations = []
            for warehouse in self.warehouse_ids:
                if warehouse.lot_stock_id:
                    warehouse_locations.append(warehouse.lot_stock_id.id)
                if warehouse.wh_input_stock_loc_id:
                    warehouse_locations.append(warehouse.wh_input_stock_loc_id.id)
                if warehouse.wh_output_stock_loc_id:
                    warehouse_locations.append(warehouse.wh_output_stock_loc_id.id)
            
            if warehouse_locations:
                domain.append(('location_id', 'in', warehouse_locations))
        
        if self.nomenclature_ids:
            domain.append(('nomenclature_id', 'in', self.nomenclature_ids.ids))
        
        if self.category_ids:
            domain.append(('nomenclature_id.category_id', 'child_of', self.category_ids.ids))
        
        if not self.show_zero_qty:
            domain.append(('current_qty', '>', 0))
        
        if not self.show_blocked:
            domain.append(('is_active', '=', True))
        
        _logger.info(f"Batch domain: {domain}")
        
        return domain

    def _group_movement_data(self, movements):
        """Групує дані рухів відповідно до рівня деталізації"""
        grouped_data = {}
        
        for movement in movements:
            key = self._get_movement_group_key(movement)
            
            if key not in grouped_data:
                grouped_data[key] = {
                    'key': key,
                    'name': self._get_group_name(movement, 'movement'),
                    'qty_in': 0.0,
                    'qty_out': 0.0,
                    'movements_count': 0,
                    'movements': [],
                    'uom_name': movement.uom_id.name if movement.uom_id else '',
                }
            
            if movement.movement_type == 'in':
                grouped_data[key]['qty_in'] += movement.qty
            elif movement.movement_type == 'out':
                grouped_data[key]['qty_out'] += movement.qty
            
            grouped_data[key]['movements_count'] += 1
            grouped_data[key]['movements'].append(movement.id)
            grouped_data[key]['qty_total'] = grouped_data[key]['qty_in'] + grouped_data[key]['qty_out']
        
        return list(grouped_data.values())

    def _group_balance_data(self, batches):
        """Групує дані залишків відповідно до рівня деталізації"""
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Grouping {len(batches)} batches for balance report")
        
        grouped_data = {}
        
        for batch in batches:
            key = self._get_balance_group_key(batch)
            
            if key not in grouped_data:
                grouped_data[key] = {
                    'key': key,
                    'name': self._get_group_name(batch, 'balance'),
                    'company_name': batch.company_id.name,  # Додаємо компанію
                    'total_qty': 0.0,
                    'available_qty': 0.0,
                    'batches_count': 0,
                    'batches': [],
                    'states': set(),
                    'uom_name': batch.uom_id.name if batch.uom_id else '',
                }
            
            grouped_data[key]['total_qty'] += batch.current_qty
            grouped_data[key]['available_qty'] += batch.available_qty
            grouped_data[key]['batches_count'] += 1
            grouped_data[key]['batches'].append(batch.id)
            grouped_data[key]['states'].add(batch.state)
        
        # Визначаємо загальний статус для групи
        for data in grouped_data.values():
            states = data['states']
            if len(states) == 1:
                data['state'] = list(states)[0]
            else:
                data['state'] = 'mixed'
            # Прибираємо set для серіалізації
            del data['states']
        
        result = list(grouped_data.values())
        _logger.info(f"Grouped balance data: {len(result)} groups")
        
        return result
    
    def _get_group_name(self, record, record_type):
        """Повертає назву групи для відображення"""
        if record_type == 'movement':
            if self.detail_level == 'warehouse':
                warehouse = record.location_from_id.warehouse_id or record.location_to_id.warehouse_id
                return warehouse.name if warehouse else 'Невизначений склад'
            elif self.detail_level == 'nomenclature':
                return record.batch_id.nomenclature_id.name
            else:  # batch
                return f"{record.batch_id.batch_number} ({record.batch_id.nomenclature_id.name})"
        else:  # balance
            if self.detail_level == 'warehouse':
                return record.location_id.warehouse_id.name if record.location_id.warehouse_id else 'Невизначений склад'
            elif self.detail_level == 'nomenclature':
                return record.nomenclature_id.name
            else:  # batch
                return f"{record.batch_number} ({record.nomenclature_id.name})"

    def _get_movement_group_key(self, movement):
        """Повертає ключ групування для руху"""
        if self.detail_level == 'warehouse':
            warehouse = movement.location_from_id.warehouse_id or movement.location_to_id.warehouse_id
            return f"warehouse_{warehouse.id if warehouse else 0}"
        elif self.detail_level == 'nomenclature':
            return f"nomenclature_{movement.batch_id.nomenclature_id.id}"
        else:  # batch
            return f"batch_{movement.batch_id.id}"

    def _get_balance_group_key(self, batch):
        """Повертає ключ групування для залишку"""
        if self.detail_level == 'warehouse':
            return f"warehouse_{batch.location_id.warehouse_id.id if batch.location_id.warehouse_id else 0}"
        elif self.detail_level == 'nomenclature':
            return f"nomenclature_{batch.nomenclature_id.id}"
        else:  # batch
            return f"batch_{batch.id}"

    def _create_movement_report_records(self, report_data):
        """Створює записи для звіту руху товарів"""
        MovementReport = self.env['stock.batch.movement.report']
        
        # Очищаємо попередні записи
        MovementReport.search([]).unlink()
        
        records = []
        for data in report_data:
            record_vals = {
                'wizard_id': self.id,
                'qty_in': data['qty_in'],
                'qty_out': data['qty_out'],
                'movements_count': data['movements_count'],
            }
            
            # Заповнюємо поля залежно від рівня деталізації
            key_parts = data['key'].split('_')
            key_type = key_parts[0]
            key_id = int(key_parts[1]) if len(key_parts) > 1 and key_parts[1].isdigit() else None
            
            if key_type == 'warehouse' and key_id:
                warehouse = self.env['stock.warehouse'].browse(key_id)
                record_vals.update({
                    'warehouse_id': warehouse.id,
                    'uom_id': warehouse.company_id.currency_id.id if warehouse else None,
                })
            elif key_type == 'nomenclature' and key_id:
                nomenclature = self.env['product.nomenclature'].browse(key_id)
                if nomenclature.exists():
                    record_vals.update({
                        'nomenclature_id': nomenclature.id,
                        'category_id': nomenclature.categ_id.id if hasattr(nomenclature, 'categ_id') else None,
                        'uom_id': nomenclature.uom_id.id if hasattr(nomenclature, 'uom_id') else None,
                    })
            elif key_type == 'batch' and key_id:
                batch = self.env['stock.batch'].browse(key_id)
                if batch.exists():
                    record_vals.update({
                        'batch_id': batch.id,
                        'nomenclature_id': batch.nomenclature_id.id,
                        'warehouse_id': batch.location_id.warehouse_id.id if batch.location_id.warehouse_id else None,
                        'category_id': batch.nomenclature_id.categ_id.id if hasattr(batch.nomenclature_id, 'categ_id') else None,
                        'uom_id': batch.uom_id.id,
                    })
            
            records.append(MovementReport.create(record_vals))
        
        return MovementReport.browse([r.id for r in records])

    def _create_balance_report_records(self, report_data):
        """Створює записи для звіту залишків товарів"""
        BalanceReport = self.env['stock.batch.balance.report']
        
        # Очищаємо попередні записи
        BalanceReport.search([]).unlink()
        
        records = []
        for data in report_data:
            record_vals = {
                'wizard_id': self.id,
                'total_qty': data['total_qty'],
                'available_qty': data['available_qty'],
                'reserved_qty': data['reserved_qty'],
                'batches_count': data['batches_count'],
                'state': data.get('state', 'mixed'),
            }
            
            # Заповнюємо поля залежно від рівня деталізації
            key_parts = data['key'].split('_')
            key_type = key_parts[0]
            key_id = int(key_parts[1]) if len(key_parts) > 1 and key_parts[1].isdigit() else None
            
            if key_type == 'warehouse' and key_id:
                warehouse = self.env['stock.warehouse'].browse(key_id)
                record_vals.update({
                    'warehouse_id': warehouse.id,
                })
            elif key_type == 'nomenclature' and key_id:
                nomenclature = self.env['product.nomenclature'].browse(key_id)
                if nomenclature.exists():
                    record_vals.update({
                        'nomenclature_id': nomenclature.id,
                        'category_id': nomenclature.categ_id.id if hasattr(nomenclature, 'categ_id') else None,
                        'uom_id': nomenclature.uom_id.id if hasattr(nomenclature, 'uom_id') else None,
                    })
            elif key_type == 'batch' and key_id:
                batch = self.env['stock.batch'].browse(key_id)
                if batch.exists():
                    record_vals.update({
                        'batch_id': batch.id,
                        'nomenclature_id': batch.nomenclature_id.id,
                        'warehouse_id': batch.location_id.warehouse_id.id if batch.location_id.warehouse_id else None,
                        'category_id': batch.nomenclature_id.categ_id.id if hasattr(batch.nomenclature_id, 'categ_id') else None,
                        'uom_id': batch.uom_id.id,
                        'state': batch.state,
                    })
            
            records.append(BalanceReport.create(record_vals))
        
        return BalanceReport.browse([r.id for r in records])

    def get_movement_report_data(self):
        """Повертає дані для звіту руху товарів"""
        domain = self._get_movement_domain()
        movements = self.env['stock.batch.movement'].search(domain, order='date desc')
        return self._group_movement_data(movements)
    
    def get_balance_report_data(self):
        """Повертає дані для звіту залишків товарів"""
        domain = self._get_batch_domain()
        batches = self.env['stock.batch'].search(domain)
        return self._group_balance_data(batches)
    
    def get_report_title(self):
        """Повертає заголовок звіту"""
        report_types = dict(self._fields['report_type'].selection)
        detail_levels = dict(self._fields['detail_level'].selection)
        
        return f"{report_types.get(self.report_type, '')} ({detail_levels.get(self.detail_level, '')})"
    
    def get_company_info(self):
        """Повертає інформацію про компанію"""
        return {
            'name': self.company_id.name,
            'period': f"{self.date_from.strftime('%d.%m.%Y')} - {self.date_to.strftime('%d.%m.%Y')}" if self.report_type == 'movement' else f"Дата звіту: {self.date_to.strftime('%d.%m.%Y')}",
            'warehouses': ', '.join(self.warehouse_ids.mapped('name')) if self.warehouse_ids else 'Всі склади',
            'categories': ', '.join(self.category_ids.mapped('complete_name')) if self.category_ids else 'Всі категорії',
        }
    
    def _is_parent_company_selected(self):
        """Перевіряє, чи вибрана головна компанія"""
        current_company = self.company_id
        parent_company = current_company.parent_id or current_company
        return current_company == parent_company
        """Експортує звіт в Excel"""
        self.ensure_one()
        
        # Тут буде логіка експорту в Excel
        # Поки що повертаємо повідомлення
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Експорт'),
                'message': _('Функція експорту в Excel буде реалізована пізніше'),
                'type': 'info',
            }
        }
        """Експортує звіт в Excel"""
        self.ensure_one()
        
        # Тут буде логіка експорту в Excel
        # Поки що повертаємо повідомлення
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Експорт'),
                'message': _('Функція експорту в Excel буде реалізована пізніше'),
                'type': 'info',
            }
        }