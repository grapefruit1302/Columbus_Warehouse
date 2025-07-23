from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class StockBalanceMovement(models.Model):
    """
    Модель для обліку рухів залишків товарів (надходження, списання, переміщення, коригування).
    """
    _name = 'stock.balance.movement'
    _description = 'Рух залишків товарів'
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    nomenclature_id = fields.Many2one(
        'product.nomenclature', 
        string='Номенклатура', 
        required=True,
        index=True
    )
    movement_type = fields.Selection([
        ('in', 'Надходження'),
        ('out', 'Списання'),
        ('transfer_in', 'Переміщення (надходження)'),
        ('transfer_out', 'Переміщення (списання)'),
        ('adjustment', 'Коригування'),
    ], string='Тип руху', required=True)
    operation_type = fields.Selection([
        ('receipt', 'Прихідна накладна'),
        ('disposal', 'Акт оприходування'),
        ('return_service', 'Повернення з сервісу'),
        ('transfer', 'Переміщення'),
        ('inventory', 'Інвентаризація'),
        ('writeoff', 'Списання'),
        ('consumption', 'Споживання'),
        ('adjustment', 'Коригування'),
    ], string='Тип операції', required=True)
    # Локації
    location_from_type = fields.Selection([
        ('warehouse', 'Склад'),
        ('employee', 'Працівник'),
        ('external', 'Зовнішня'),
    ], string='Тип локації (з)')
    location_to_type = fields.Selection([
        ('warehouse', 'Склад'),
        ('employee', 'Працівник'),
        ('external', 'Зовнішня'),
    ], string='Тип локації (в)')
    warehouse_from_id = fields.Many2one('stock.warehouse', string='Склад (з)')
    warehouse_to_id = fields.Many2one('stock.warehouse', string='Склад (в)')
    employee_from_id = fields.Many2one('hr.employee', string='Працівник (з)')
    employee_to_id = fields.Many2one('hr.employee', string='Працівник (в)')
    location_from_id = fields.Many2one('stock.location', string='Локація (з)')
    location_to_id = fields.Many2one('stock.location', string='Локація (в)')
    batch_id = fields.Many2one('stock.batch', string='Партія')
    qty = fields.Float(
        string='Кількість', 
        required=True,
        digits='Product Unit of Measure'
    )
    uom_id = fields.Many2one(
        'uom.uom', 
        string='Одиниця виміру', 
        required=True
    )
    date = fields.Datetime(
        string='Дата та час', 
        required=True,
        default=fields.Datetime.now,
        index=True
    )
    document_reference = fields.Char(
        string='Документ', 
        help='Посилання на документ, що спричинив рух'
    )
    company_id = fields.Many2one(
        'res.company', 
        string='Компанія', 
        required=True,
        default=lambda self: self.env.company
    )
    user_id = fields.Many2one(
        'res.users', 
        string='Користувач', 
        required=True,
        default=lambda self: self.env.user
    )
    notes = fields.Text(string='Примітки')
    serial_numbers = fields.Text(string='Серійні номери')
    display_name = fields.Char(
        string='Назва',
        compute='_compute_display_name',
        store=True
    )
    balance_before = fields.Float(string='Залишок до', readonly=True)
    balance_after = fields.Float(string='Залишок після', readonly=True)
    balance_id = fields.Many2one(
        'stock.balance',
        string='Залишок',
        readonly=True,
        ondelete='set null',
        index=True
    )
    tracking_serial = fields.Boolean(
        string='Облік по серійних',
        related='balance_id.tracking_serial',
        store=True,
        readonly=True,
    )

    @api.depends('movement_type', 'operation_type', 'nomenclature_id', 'qty', 'date')
    def _compute_display_name(self):
        """Генерує відображувану назву руху залишків"""
        for movement in self:
            operation_label = dict(movement._fields['operation_type'].selection).get(
                movement.operation_type, movement.operation_type
            )
            movement_label = dict(movement._fields['movement_type'].selection).get(
                movement.movement_type, movement.movement_type
            )
            name_parts = [
                operation_label,
                movement.nomenclature_id.name if movement.nomenclature_id else '',
                f"{movement.qty} {movement.uom_id.name if movement.uom_id else ''}",
                movement.date.strftime('%d.%m.%Y %H:%M') if movement.date else ''
            ]
            movement.display_name = " | ".join(filter(None, name_parts))

    @api.model
    def create_movement(self, nomenclature_id, qty, movement_type, operation_type,
                       location_from_type=None, location_to_type=None,
                       warehouse_from_id=None, warehouse_to_id=None,
                       employee_from_id=None, employee_to_id=None,
                       location_from_id=None, location_to_id=None,
                       batch_id=None, uom_id=None, document_reference=None,
                       notes=None, serial_numbers=None, company_id=None, date=None):
        """
        Створює рух залишків та оновлює баланси, зберігає залишок до/після.
        """
        if company_id is None:
            company_id = self.env.company.id
        if uom_id is None:
            nomenclature = self.env['product.nomenclature'].browse(nomenclature_id)
            uom_id = nomenclature.base_uom_id.id
        if date is None:
            date = fields.Datetime.now()
        # Визначаємо залишок до руху
        Balance = self.env['stock.balance']
        domain = [
            ('nomenclature_id', '=', nomenclature_id),
            ('company_id', '=', company_id),
        ]
        if location_from_type == 'warehouse':
            domain += [('location_type', '=', 'warehouse'), ('warehouse_id', '=', warehouse_from_id)]
            if location_from_id:
                domain += [('location_id', '=', location_from_id)]
        elif location_from_type == 'employee':
            domain += [('location_type', '=', 'employee'), ('employee_id', '=', employee_from_id)]
        if batch_id:
            domain += [('batch_id', '=', batch_id)]
        else:
            domain += [('batch_id', '=', False)]
        balance_before = 0.0
        balance_after = 0.0
        balance_rec = Balance.search(domain, limit=1)
        if balance_rec:
            balance_before = balance_rec.qty_on_hand
        movement_vals = {
            'nomenclature_id': nomenclature_id,
            'movement_type': movement_type,
            'operation_type': operation_type,
            'qty': qty,
            'uom_id': uom_id,
            'date': date,
            'document_reference': document_reference,
            'notes': notes,
            'serial_numbers': serial_numbers,
            'company_id': company_id,
            'batch_id': batch_id,
            'location_from_type': location_from_type,
            'location_to_type': location_to_type,
            'warehouse_from_id': warehouse_from_id,
            'warehouse_to_id': warehouse_to_id,
            'employee_from_id': employee_from_id,
            'employee_to_id': employee_to_id,
            'location_from_id': location_from_id,
            'location_to_id': location_to_id,
            'balance_before': balance_before,
            'balance_id': balance_rec.id if balance_rec else False,
        }
        movement = self.create(movement_vals)
        self._update_balances_from_movement(movement)
        # Визначаємо залишок після руху
        balance_rec_after = Balance.search(domain, limit=1)
        if balance_rec_after:
            movement.balance_after = balance_rec_after.qty_on_hand
        else:
            movement.balance_after = 0.0
        return movement

    def _update_balances_from_movement(self, movement):
        """
        Оновлює баланси на основі руху (списання з джерела, надходження в призначення).
        """
        Balance = self.env['stock.balance']
        # Списання з локації відправлення
        if movement.location_from_type in ['warehouse', 'employee']:
            if movement.location_from_type == 'warehouse':
                Balance.update_balance(
                    nomenclature_id=movement.nomenclature_id.id,
                    qty_change=-movement.qty,
                    location_type='warehouse',
                    warehouse_id=movement.warehouse_from_id.id,
                    location_id=movement.location_from_id.id if movement.location_from_id else None,
                    batch_id=movement.batch_id.id if movement.batch_id else None,
                    uom_id=movement.uom_id.id,
                    company_id=movement.company_id.id,
                )
            else:  # employee
                Balance.update_balance(
                    nomenclature_id=movement.nomenclature_id.id,
                    qty_change=-movement.qty,
                    location_type='employee',
                    employee_id=movement.employee_from_id.id,
                    batch_id=movement.batch_id.id if movement.batch_id else None,
                    uom_id=movement.uom_id.id,
                    company_id=movement.company_id.id,
                )
        # Надходження в локацію призначення
        if movement.location_to_type in ['warehouse', 'employee']:
            if movement.location_to_type == 'warehouse':
                Balance.update_balance(
                    nomenclature_id=movement.nomenclature_id.id,
                    qty_change=movement.qty,
                    location_type='warehouse',
                    warehouse_id=movement.warehouse_to_id.id,
                    location_id=movement.location_to_id.id if movement.location_to_id else None,
                    batch_id=movement.batch_id.id if movement.batch_id else None,
                    uom_id=movement.uom_id.id,
                    company_id=movement.company_id.id,
                    serial_numbers=movement.serial_numbers,
                )
            else:  # employee
                Balance.update_balance(
                    nomenclature_id=movement.nomenclature_id.id,
                    qty_change=movement.qty,
                    location_type='employee',
                    employee_id=movement.employee_to_id.id,
                    batch_id=movement.batch_id.id if movement.batch_id else None,
                    uom_id=movement.uom_id.id,
                    company_id=movement.company_id.id,
                    serial_numbers=movement.serial_numbers,
                )