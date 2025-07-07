# stock_balance_management/models/stock_transfer_serial_wizard.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class StockTransferSerialWizard(models.TransientModel):
    _name = 'stock.transfer.serial.wizard'
    _description = 'Wizard для вибору серійних номерів при переміщенні'

    transfer_id = fields.Many2one('stock.transfer', 'Переміщення', required=True)
    nomenclature_id = fields.Many2one('product.nomenclature', 'Номенклатура', required=True)
    nomenclature_name = fields.Char('Товар', related='nomenclature_id.name', readonly=True)
    
    # Інформація про локації
    location_from_type = fields.Selection([
        ('warehouse', 'Склад'),
        ('employee', 'Працівник'),
    ], 'Тип локації (з)', related='transfer_id.transfer_type', readonly=True)
    
    warehouse_from_id = fields.Many2one('stock.warehouse', 'Склад (з)', 
                                       related='transfer_id.warehouse_from_id', readonly=True)
    employee_from_id = fields.Many2one('hr.employee', 'Працівник (з)', 
                                      related='transfer_id.employee_from_id', readonly=True)
    
    location_to_type = fields.Selection([
        ('warehouse', 'Склад'),
        ('employee', 'Працівник'),
    ], 'Тип локації (в)', compute='_compute_location_to_type', readonly=True)
    
    warehouse_to_id = fields.Many2one('stock.warehouse', 'Склад (в)', 
                                     related='transfer_id.warehouse_to_id', readonly=True)
    employee_to_id = fields.Many2one('hr.employee', 'Працівник (в)', 
                                    related='transfer_id.employee_to_id', readonly=True)
    
    # Доступні залишки та серійні номери
    available_balance_ids = fields.One2many('stock.transfer.serial.balance.line', 'wizard_id', 
                                           'Доступні залишки')
    
    # Обрані серійні номери
    selected_serial_ids = fields.One2many('stock.transfer.serial.selected.line', 'wizard_id', 
                                         'Обрані серійні номери')
    
    # Загальна інформація
    total_available_qty = fields.Float('Доступна кількість', compute='_compute_totals', readonly=True)
    total_selected_qty = fields.Float('Обрана кількість', compute='_compute_totals', readonly=True)
    required_qty = fields.Float('Потрібна кількість', required=True)
    
    @api.depends('transfer_id.transfer_type')
    def _compute_location_to_type(self):
        for wizard in self:
            if wizard.transfer_id.transfer_type == 'warehouse':
                wizard.location_to_type = 'warehouse'
            elif wizard.transfer_id.transfer_type == 'employee':
                wizard.location_to_type = 'employee'
            else:
                wizard.location_to_type = False

    @api.depends('available_balance_ids.qty_available', 'selected_serial_ids')
    def _compute_totals(self):
        for wizard in self:
            wizard.total_available_qty = sum(wizard.available_balance_ids.mapped('qty_available'))
            wizard.total_selected_qty = len(wizard.selected_serial_ids)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        
        transfer_id = self.env.context.get('default_transfer_id')
        nomenclature_id = self.env.context.get('default_nomenclature_id')
        required_qty = self.env.context.get('default_required_qty', 1.0)
        
        if transfer_id and nomenclature_id:
            res.update({
                'transfer_id': transfer_id,
                'nomenclature_id': nomenclature_id,
                'required_qty': required_qty,
            })
            
            # Завантажуємо доступні залишки
            wizard = self.new(res)
            wizard._load_available_balances()
            res['available_balance_ids'] = [(0, 0, {
                'balance_id': balance.id,
                'batch_id': balance.batch_id.id if balance.batch_id else False,
                'qty_available': balance.qty_available,
            }) for balance in wizard._get_available_balances()]
        
        return res

    def _get_available_balances(self):
        """Отримує доступні залишки для переміщення"""
        domain = [
            ('nomenclature_id', '=', self.nomenclature_id.id),
            ('qty_available', '>', 0),
            ('company_id', 'in', self._get_transfer_companies()),
        ]
        
        # Додаємо умови залежно від типу переміщення
        if self.transfer_id.transfer_type == 'warehouse':
            domain.append(('location_type', '=', 'warehouse'))
            domain.append(('warehouse_id', '=', self.warehouse_from_id.id))
        elif self.transfer_id.transfer_type == 'employee':
            domain.append(('location_type', '=', 'employee'))
            domain.append(('employee_id', '=', self.employee_from_id.id))
        elif self.transfer_id.transfer_type == 'to_employee':
            domain.append(('location_type', '=', 'warehouse'))
            domain.append(('warehouse_id', '=', self.warehouse_from_id.id))
        elif self.transfer_id.transfer_type == 'from_employee':
            domain.append(('location_type', '=', 'employee'))
            domain.append(('employee_id', '=', self.employee_from_id.id))
        
        # Тільки з серійними номерами
        domain.append(('serial_numbers', '!=', False))
        domain.append(('serial_numbers', '!=', ''))
        
        return self.env['stock.balance'].search(domain, order='batch_id.date_created ASC, id ASC')

    def _get_transfer_companies(self):
        """Отримує компанії для пошуку залишків"""
        companies = [self.transfer_id.company_id.id]
        companies.extend(self.transfer_id.company_id.child_ids.ids)
        return companies

    def _load_available_balances(self):
        """Завантажує доступні залишки"""
        balances = self._get_available_balances()
        balance_lines = []
        
        for balance in balances:
            balance_lines.append((0, 0, {
                'balance_id': balance.id,
                'batch_id': balance.batch_id.id if balance.batch_id else False,
                'qty_available': balance.qty_available,
            }))
        
        self.available_balance_ids = balance_lines

    def action_load_serial_numbers(self, balance_id):
        """Завантажує серійні номери з обраного залишку"""
        balance = self.env['stock.balance'].browse(balance_id)
        if not balance.exists():
            raise UserError(_('Залишок не знайдено'))
        
        serial_numbers = balance.get_serial_numbers_list()
        if not serial_numbers:
            raise UserError(_('В цьому залишку немає серійних номерів'))
        
        # Додаємо серійні номери до обраних
        selected_lines = []
        for serial in serial_numbers:
            # Перевіряємо, чи не дублюється серійний номер
            existing = self.selected_serial_ids.filtered(lambda x: x.serial_number == serial)
            if not existing:
                selected_lines.append((0, 0, {
                    'balance_id': balance_id,
                    'batch_id': balance.batch_id.id if balance.batch_id else False,
                    'serial_number': serial,
                }))
        
        if selected_lines:
            self.selected_serial_ids = selected_lines
        else:
            raise UserError(_('Всі серійні номери з цього залишку вже обрані'))
        
        return True

    def action_remove_serial_number(self, serial_line_id):
        """Видаляє серійний номер з обраних"""
        serial_line = self.selected_serial_ids.browse(serial_line_id)
        if serial_line.exists():
            serial_line.unlink()
        return True

    def action_confirm_selection(self):
        """Підтверджує вибір серійних номерів та створює переміщення"""
        if not self.selected_serial_ids:
            raise UserError(_('Оберіть хоча б один серійний номер'))
        
        if len(self.selected_serial_ids) != self.required_qty:
            raise UserError(_('Кількість обраних серійних номерів (%s) не відповідає потрібній кількості (%s)') % 
                           (len(self.selected_serial_ids), self.required_qty))
        
        # Групуємо серійні номери за залишками/партіями
        movements_to_create = self._prepare_movements_data()
        
        # Створюємо рухи
        for movement_data in movements_to_create:
            self._create_movement(movement_data)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Переміщення створено'),
                'message': _('Успішно створено переміщення для %s серійних номерів') % len(self.selected_serial_ids),
                'type': 'success',
            }
        }

    def _prepare_movements_data(self):
        """Підготовлює дані для створення рухів"""
        movements = {}
        
        for serial_line in self.selected_serial_ids:
            balance = serial_line.balance_id
            key = (balance.id, serial_line.batch_id.id if serial_line.batch_id else None)
            
            if key not in movements:
                movements[key] = {
                    'balance': balance,
                    'batch_id': serial_line.batch_id.id if serial_line.batch_id else None,
                    'serial_numbers': [],
                    'qty': 0,
                }
            
            movements[key]['serial_numbers'].append(serial_line.serial_number)
            movements[key]['qty'] += 1
        
        return list(movements.values())

    def _create_movement(self, movement_data):
        """Створює рух залишків"""
        balance = movement_data['balance']
        serial_numbers_str = ','.join(movement_data['serial_numbers'])
        
        # Визначаємо параметри руху
        movement_vals = {
            'nomenclature_id': self.nomenclature_id.id,
            'qty': movement_data['qty'],
            'movement_type': 'transfer_out',
            'operation_type': 'transfer',
            'batch_id': movement_data['batch_id'],
            'uom_id': self.nomenclature_id.base_uom_id.id,
            'document_reference': self.transfer_id.number,
            'notes': f'Переміщення {self.transfer_id.number}',
            'serial_numbers': serial_numbers_str,
            'company_id': balance.company_id.id,
            'date': self.transfer_id.posting_datetime or fields.Datetime.now(),
        }
        
        # Додаємо інформацію про локації
        if self.transfer_id.transfer_type == 'warehouse':
            movement_vals.update({
                'location_from_type': 'warehouse',
                'location_to_type': 'warehouse',
                'warehouse_from_id': self.warehouse_from_id.id,
                'warehouse_to_id': self.warehouse_to_id.id,
                'location_from_id': self.warehouse_from_id.lot_stock_id.id,
                'location_to_id': self.warehouse_to_id.lot_stock_id.id,
            })
        elif self.transfer_id.transfer_type == 'employee':
            movement_vals.update({
                'location_from_type': 'employee',
                'location_to_type': 'employee',
                'employee_from_id': self.employee_from_id.id,
                'employee_to_id': self.employee_to_id.id,
            })
        elif self.transfer_id.transfer_type == 'to_employee':
            movement_vals.update({
                'location_from_type': 'warehouse',
                'location_to_type': 'employee',
                'warehouse_from_id': self.warehouse_from_id.id,
                'employee_to_id': self.employee_to_id.id,
                'location_from_id': self.warehouse_from_id.lot_stock_id.id,
            })
        elif self.transfer_id.transfer_type == 'from_employee':
            movement_vals.update({
                'location_from_type': 'employee',
                'location_to_type': 'warehouse',
                'employee_from_id': self.employee_from_id.id,
                'warehouse_to_id': self.warehouse_to_id.id,
                'location_to_id': self.warehouse_to_id.lot_stock_id.id,
            })
        
        # Створюємо рух
        self.env['stock.balance.movement'].create_movement(**movement_vals)


class StockTransferSerialBalanceLine(models.TransientModel):
    _name = 'stock.transfer.serial.balance.line'
    _description = 'Рядок доступного залишку'

    wizard_id = fields.Many2one('stock.transfer.serial.wizard', 'Wizard', required=True, ondelete='cascade')
    balance_id = fields.Many2one('stock.balance', 'Залишок', required=True)
    batch_id = fields.Many2one('stock.batch', 'Партія')
    batch_number = fields.Char('Номер партії', related='batch_id.batch_number', readonly=True)
    qty_available = fields.Float('Доступна кількість', readonly=True)
    serial_count = fields.Integer('Кількість S/N', compute='_compute_serial_count')
    
    @api.depends('balance_id')
    def _compute_serial_count(self):
        for line in self:
            if line.balance_id and line.balance_id.serial_numbers:
                line.serial_count = len(line.balance_id.get_serial_numbers_list())
            else:
                line.serial_count = 0
    
    def action_load_serials(self):
        """Завантажує серійні номери з цього залишку"""
        return self.wizard_id.action_load_serial_numbers(self.balance_id.id)


class StockTransferSerialSelectedLine(models.TransientModel):
    _name = 'stock.transfer.serial.selected.line'
    _description = 'Обраний серійний номер'

    wizard_id = fields.Many2one('stock.transfer.serial.wizard', 'Wizard', required=True, ondelete='cascade')
    balance_id = fields.Many2one('stock.balance', 'Залишок', required=True)
    batch_id = fields.Many2one('stock.batch', 'Партія')
    batch_number = fields.Char('Номер партії', related='batch_id.batch_number', readonly=True)
    serial_number = fields.Char('Серійний номер', required=True)
    
    def action_remove(self):
        """Видаляє цей серійний номер з обраних"""
        return self.wizard_id.action_remove_serial_number(self.id)