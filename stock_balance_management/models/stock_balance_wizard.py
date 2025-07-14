from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class StockBalanceReportWizard(models.TransientModel):
    _name = 'stock.balance.report.wizard'
    _description = 'Wizard для звітів по залишках'

    report_type = fields.Selection([
        ('summary', 'Зведений звіт'),
        ('detailed', 'Детальний звіт'),
        ('by_employee', 'По працівниках'),
        ('by_warehouse', 'По складах'),
        ('by_batch', 'По партіях'),
    ], 'Тип звіту', required=True, default='summary')

    date_from = fields.Date('Дата з', required=True, default=fields.Date.today)
    date_to = fields.Date('Дата по', required=True, default=fields.Date.today)

    company_id = fields.Many2one(
        'res.company', 
        'Компанія',
        required=True,
        default=lambda self: self.env.company
    )

    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        'balance_report_warehouse_rel',
        'wizard_id',
        'warehouse_id',
        'Склади'
    )

    employee_ids = fields.Many2many(
        'hr.employee',
        'balance_report_employee_rel',
        'wizard_id',
        'employee_id',
        'Працівники'
    )

    nomenclature_ids = fields.Many2many(
        'product.nomenclature',
        'balance_report_nomenclature_rel',
        'wizard_id',
        'nomenclature_id',
        'Номенклатура'
    )

    category_ids = fields.Many2many(
        'product.nomenclature.category',
        'balance_report_category_rel',
        'wizard_id',
        'category_id',
        'Категорії товарів'
    )

    show_zero_qty = fields.Boolean(
        'Показувати нульові залишки',
        default=False
    )

    show_movements = fields.Boolean(
        'Показувати рухи',
        default=False
    )

    def action_generate_report(self):
        """Генерує звіт по залишках"""
        self.ensure_one()
        
        domain = self._get_balance_domain()
        balances = self.env['stock.balance'].search(domain)
        
        if self.report_type == 'by_employee':
            return self._generate_employee_report(balances)
        elif self.report_type == 'by_warehouse':
            return self._generate_warehouse_report(balances)
        elif self.report_type == 'by_batch':
            return self._generate_batch_report(balances)
        else:
            return self._generate_summary_report(balances)

    def _get_balance_domain(self):
        """Формує domain для пошуку залишків"""
        domain = [('company_id', '=', self.company_id.id)]
        
        if not self.show_zero_qty:
            domain.append(('qty_available', '>', 0))
        
        if self.warehouse_ids:
            domain.append(('warehouse_id', 'in', self.warehouse_ids.ids))
        
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        
        if self.nomenclature_ids:
            domain.append(('nomenclature_id', 'in', self.nomenclature_ids.ids))
        
        if self.category_ids:
            domain.append(('nomenclature_id.category_id', 'child_of', self.category_ids.ids))
        
        return domain

    def _generate_summary_report(self, balances):
        """Генерує зведений звіт"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Зведений звіт по залишках',
            'res_model': 'stock.balance',
            'view_mode': 'list',
            'domain': [('id', 'in', balances.ids)],
            'context': {
                'group_by': ['nomenclature_id'],
                'search_default_group_by_nomenclature': 1,
            }
        }

    def _generate_employee_report(self, balances):
        """Генерує звіт по працівниках"""
        employee_balances = balances.filtered(lambda b: b.location_type == 'employee')
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Звіт по залишках у працівників',
            'res_model': 'stock.balance',
            'view_mode': 'list',
            'domain': [('id', 'in', employee_balances.ids)],
            'context': {
                'group_by': ['employee_id', 'nomenclature_id'],
                'search_default_group_by_employee': 1,
            }
        }

    def _generate_warehouse_report(self, balances):
        """Генерує звіт по складах"""
        warehouse_balances = balances.filtered(lambda b: b.location_type == 'warehouse')
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Звіт по залишках на складах',
            'res_model': 'stock.balance',
            'view_mode': 'list',
            'domain': [('id', 'in', warehouse_balances.ids)],
            'context': {
                'group_by': ['warehouse_id', 'nomenclature_id'],
                'search_default_group_by_warehouse': 1,
            }
        }

    def _generate_batch_report(self, balances):
        """Генерує звіт по партіях"""
        batch_balances = balances.filtered(lambda b: b.batch_id)
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Звіт по залишках партій',
            'res_model': 'stock.balance',
            'view_mode': 'list',
            'domain': [('id', 'in', batch_balances.ids)],
            'context': {
                'group_by': ['batch_id', 'nomenclature_id'],
                'search_default_group_by_batch': 1,
            }
        }


class StockBalanceAdjustmentWizard(models.TransientModel):
    _name = 'stock.balance.adjustment.wizard'
    _description = 'Wizard для коригування залишків'

    nomenclature_id = fields.Many2one(
        'product.nomenclature',
        'Номенклатура',
        required=True
    )

    location_type = fields.Selection([
        ('warehouse', 'Склад'),
        ('employee', 'Працівник'),
    ], 'Тип локації', required=True, default='warehouse')

    location_type_display = fields.Char(
        string='Тип локації',
        compute='_compute_location_type_display',
        store=False
    )

    @api.depends('location_type')
    def _compute_location_type_display(self):
        for rec in self:
            if rec.location_type == 'warehouse':
                rec.location_type_display = 'Склад'
            elif rec.location_type == 'employee':
                rec.location_type_display = 'Працівник'
            else:
                rec.location_type_display = ''

    warehouse_id = fields.Many2one(
        'stock.warehouse',
        'Склад',
        required=False
    )

    employee_id = fields.Many2one(
        'hr.employee',
        'Працівник',
        required=False
    )

    batch_id = fields.Many2one(
        'stock.batch',
        'Партія'
    )

    current_qty = fields.Float(
        'Поточна кількість',
        readonly=True
    )

    new_qty = fields.Float(
        'Нова кількість',
        required=True
    )

    adjustment_qty = fields.Float(
        'Коригування',
        compute='_compute_adjustment_qty'
    )

    reason = fields.Text(
        'Причина коригування',
        required=True
    )

    @api.depends('current_qty', 'new_qty')
    def _compute_adjustment_qty(self):
        for wizard in self:
            wizard.adjustment_qty = wizard.new_qty - wizard.current_qty

    @api.onchange('nomenclature_id', 'location_type', 'warehouse_id', 'employee_id', 'batch_id')
    def _onchange_location(self):
        """Оновлює поточну кількість при зміні локації"""
        if self.nomenclature_id:
            Balance = self.env['stock.balance']
            
            if self.location_type == 'warehouse' and self.warehouse_id:
                self.current_qty = Balance.get_available_qty(
                    nomenclature_id=self.nomenclature_id.id,
                    location_type='warehouse',
                    warehouse_id=self.warehouse_id.id,
                    batch_id=self.batch_id.id if self.batch_id else None
                )
            elif self.location_type == 'employee' and self.employee_id:
                self.current_qty = Balance.get_available_qty(
                    nomenclature_id=self.nomenclature_id.id,
                    location_type='employee',
                    employee_id=self.employee_id.id,
                    batch_id=self.batch_id.id if self.batch_id else None
                )
            else:
                self.current_qty = 0.0

    def action_apply_adjustment(self):
        """Застосовує коригування залишків"""
        self.ensure_one()
        
        if self.adjustment_qty == 0:
            raise ValidationError(_('Коригування дорівнює нулю. Немає змін для застосування.'))
        
        # Створюємо рух коригування
        movement_type = 'in' if self.adjustment_qty > 0 else 'out'
        
        movement_vals = {
            'nomenclature_id': self.nomenclature_id.id,
            'qty': abs(self.adjustment_qty),
            'movement_type': movement_type,
            'operation_type': 'adjustment',
            'batch_id': self.batch_id.id if self.batch_id else None,
            'uom_id': self.nomenclature_id.base_uom_id.id,
            'document_reference': f'Коригування #{self.id}',
            'notes': self.reason,
        }
        
        if self.location_type == 'warehouse':
            movement_vals.update({
                'location_to_type': 'warehouse' if movement_type == 'in' else None,
                'location_from_type': 'warehouse' if movement_type == 'out' else None,
                'warehouse_to_id': self.warehouse_id.id if movement_type == 'in' else None,
                'warehouse_from_id': self.warehouse_id.id if movement_type == 'out' else None,
                'location_to_id': self.warehouse_id.lot_stock_id.id if movement_type == 'in' else None,
                'location_from_id': self.warehouse_id.lot_stock_id.id if movement_type == 'out' else None,
            })
        else:
            movement_vals.update({
                'location_to_type': 'employee' if movement_type == 'in' else None,
                'location_from_type': 'employee' if movement_type == 'out' else None,
                'employee_to_id': self.employee_id.id if movement_type == 'in' else None,
                'employee_from_id': self.employee_id.id if movement_type == 'out' else None,
            })
        
        self.env['stock.balance.movement'].create_movement(**movement_vals)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Коригування застосовано'),
                'message': _('Залишки успішно скориговано на %s') % self.adjustment_qty,
                'type': 'success',
            }
        }