# stock_balance_management/models/stock_balance_integration.py

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class StockTransferLine(models.Model):
    """Розширюємо позиції переміщень"""
    _inherit = 'stock.transfer.line'

    available_qty = fields.Float(
        'Доступна кількість',
        compute='_compute_available_qty',
        help='Доступна кількість в локації відправника'
    )

    @api.depends('nomenclature_id', 'transfer_id.transfer_type', 
                 'transfer_id.warehouse_from_id', 'transfer_id.employee_from_id')
    def _compute_available_qty(self):
        for line in self:
            if not line.nomenclature_id or not line.transfer_id:
                line.available_qty = 0.0
                continue
            
            Balance = self.env['stock.balance']
            transfer = line.transfer_id
            
            # Отримуємо всі дочірні компанії + головну
            company_ids = transfer._get_child_companies(transfer.company_id)
            
            # Простий пошук залишків з урахуванням дочірніх компаній
            if transfer.transfer_type in ['warehouse', 'warehouse_employee']:
                if transfer.warehouse_from_id:
                    domain = [
                        ('nomenclature_id', '=', line.nomenclature_id.id),
                        ('location_type', '=', 'warehouse'),
                        ('warehouse_id', '=', transfer.warehouse_from_id.id),
                        ('company_id', 'in', company_ids),
                        ('qty_available', '>', 0)
                    ]
                    balances = Balance.search(domain)
                    line.available_qty = sum(balance.qty_available for balance in balances)
                else:
                    line.available_qty = 0.0
            elif transfer.transfer_type in ['employee', 'employee_warehouse']:
                if transfer.employee_from_id:
                    domain = [
                        ('nomenclature_id', '=', line.nomenclature_id.id),
                        ('location_type', '=', 'employee'),
                        ('employee_id', '=', transfer.employee_from_id.id),
                        ('company_id', 'in', company_ids),
                        ('qty_available', '>', 0)
                    ]
                    balances = Balance.search(domain)
                    line.available_qty = sum(balance.qty_available for balance in balances)
                else:
                    line.available_qty = 0.0
            else:
                line.available_qty = 0.0

    @api.constrains('qty', 'nomenclature_id')
    def _check_qty_availability(self):
        """Перевіряє доступність товару при зміні кількості"""
        for line in self:
            if (line.qty > 0 and line.available_qty < line.qty and 
                line.transfer_id.state != 'draft'):
                raise ValidationError(
                    _('Недостатньо товару "%s". Доступно: %s, потрібно: %s') % (
                        line.nomenclature_id.name,
                        line.available_qty,
                        line.qty
                    )
                )


class StockTransfer(models.Model):
    """Розширюємо модель переміщень для роботи з залишками"""
    _inherit = 'stock.transfer'

    def action_done(self):
        """Перевіряємо доступність товарів перед проведенням"""
        # Спочатку перевіряємо доступність всіх товарів
        for line in self.line_ids:
            self._check_line_availability(line)
        
        # Якщо все ОК, проводимо переміщення
        result = super().action_done()
        
        # Створюємо рухи залишків
        for line in self.line_ids:
            try:
                self._create_balance_movements_for_line(line)
            except Exception as e:
                _logger.error(f"Помилка створення руху залишків для {line.nomenclature_id.name}: {e}")
                self.message_post(
                    body=_('Помилка оновлення залишків для %s: %s') % (line.nomenclature_id.name, str(e)),
                    message_type='notification'
                )
        
        return result

    def _check_line_availability(self, line):
        """Перевіряє доступність товару для переміщення"""
        Balance = self.env['stock.balance']
        
        # Отримуємо всі дочірні компанії + головну
        company_ids = self._get_child_companies(self.company_id)
        
        # Визначаємо локацію відправника та рахуємо доступну кількість
        if self.transfer_type == 'warehouse':
            domain = [
                ('nomenclature_id', '=', line.nomenclature_id.id),
                ('location_type', '=', 'warehouse'),
                ('warehouse_id', '=', self.warehouse_from_id.id),
                ('company_id', 'in', company_ids),
                ('qty_available', '>', 0)
            ]
            balances = Balance.search(domain)
            available_qty = sum(balance.qty_available for balance in balances)
            location_name = self.warehouse_from_id.name
            
        elif self.transfer_type == 'employee':
            domain = [
                ('nomenclature_id', '=', line.nomenclature_id.id),
                ('location_type', '=', 'employee'),
                ('employee_id', '=', self.employee_from_id.id),
                ('company_id', 'in', company_ids),
                ('qty_available', '>', 0)
            ]
            balances = Balance.search(domain)
            available_qty = sum(balance.qty_available for balance in balances)
            location_name = self.employee_from_id.name
            
        elif self.transfer_type == 'employee_warehouse':
            domain = [
                ('nomenclature_id', '=', line.nomenclature_id.id),
                ('location_type', '=', 'employee'),
                ('employee_id', '=', self.employee_from_id.id),
                ('company_id', 'in', company_ids),
                ('qty_available', '>', 0)
            ]
            balances = Balance.search(domain)
            available_qty = sum(balance.qty_available for balance in balances)
            location_name = self.employee_from_id.name
            
        elif self.transfer_type == 'warehouse_employee':
            domain = [
                ('nomenclature_id', '=', line.nomenclature_id.id),
                ('location_type', '=', 'warehouse'),
                ('warehouse_id', '=', self.warehouse_from_id.id),
                ('company_id', 'in', company_ids),
                ('qty_available', '>', 0)
            ]
            balances = Balance.search(domain)
            available_qty = sum(balance.qty_available for balance in balances)
            location_name = self.warehouse_from_id.name
        else:
            raise UserError(_('Невідомий тип переміщення: %s') % self.transfer_type)
        
        if available_qty < line.qty:
            raise UserError(
                _('Недостатньо товару "%s" в локації "%s".\n'
                  'Доступно: %s, потрібно: %s') % (
                    line.nomenclature_id.name,
                    location_name,
                    available_qty,
                    line.qty
                )
            )
    
    def _get_child_companies(self, company):
        """Повертає список ID головної компанії та всіх її дочірніх компаній"""
        company_ids = [company.id]
        
        # Рекурсивно додаємо всі дочірні компанії
        def add_children(parent_company):
            children = self.env['res.company'].search([('parent_id', '=', parent_company.id)])
            for child in children:
                if child.id not in company_ids:
                    company_ids.append(child.id)
                    add_children(child)  # Рекурсивно додаємо дочірні дочірніх
        
        add_children(company)
        return company_ids

    def _create_balance_movements_for_line(self, line):
        """Створює рухи залишків для позиції переміщення"""
        if line.qty <= 0:
            return
        
        Movement = self.env['stock.balance.movement']
        
        # Визначаємо параметри руху залежно від типу переміщення
        if self.transfer_type == 'warehouse':
            # Між складами
            location_from_id = self.warehouse_from_id.lot_stock_id.id
            location_to_id = self.warehouse_to_id.lot_stock_id.id
            
            # Використовуємо простий FIFO для вибору партій
            domain = [
                ('nomenclature_id', '=', line.nomenclature_id.id),
                ('location_type', '=', 'warehouse'),
                ('warehouse_id', '=', self.warehouse_from_id.id),
                ('company_id', 'in', self._get_child_companies(self.company_id)),
                ('qty_available', '>', 0)
            ]
            balances = self.env['stock.balance'].search(domain, order='batch_id ASC, id ASC')
            
            remaining_qty = line.qty
            for balance in balances:
                if remaining_qty <= 0:
                    break
                
                take_qty = min(balance.qty_available, remaining_qty)
                batch_id = balance.batch_id.id if balance.batch_id else None
                
                Movement.create_movement(
                    nomenclature_id=line.nomenclature_id.id,
                    qty=take_qty,
                    movement_type='transfer_out',
                    operation_type='transfer',
                    location_from_type='warehouse',
                    location_to_type='warehouse',
                    warehouse_from_id=self.warehouse_from_id.id,
                    warehouse_to_id=self.warehouse_to_id.id,
                    location_from_id=location_from_id,
                    location_to_id=location_to_id,
                    batch_id=batch_id,
                    uom_id=line.selected_uom_id.id,
                    document_reference=self.number,
                    notes=f'Переміщення {self.number}: {self.warehouse_from_id.name} → {self.warehouse_to_id.name}',
                    company_id=balance.company_id.id,  # Використовуємо компанію з залишку
                    date=self.posting_datetime,
                )
                
                remaining_qty -= take_qty
        
        elif self.transfer_type == 'employee':
            # Між працівниками
            domain = [
                ('nomenclature_id', '=', line.nomenclature_id.id),
                ('location_type', '=', 'employee'),
                ('employee_id', '=', self.employee_from_id.id),
                ('company_id', 'in', self._get_child_companies(self.company_id)),
                ('qty_available', '>', 0)
            ]
            balances = self.env['stock.balance'].search(domain, order='batch_id ASC, id ASC')
            
            remaining_qty = line.qty
            for balance in balances:
                if remaining_qty <= 0:
                    break
                
                take_qty = min(balance.qty_available, remaining_qty)
                batch_id = balance.batch_id.id if balance.batch_id else None
                
                Movement.create_movement(
                    nomenclature_id=line.nomenclature_id.id,
                    qty=take_qty,
                    movement_type='transfer_out',
                    operation_type='transfer',
                    location_from_type='employee',
                    location_to_type='employee',
                    employee_from_id=self.employee_from_id.id,
                    employee_to_id=self.employee_to_id.id,
                    batch_id=batch_id,
                    uom_id=line.selected_uom_id.id,
                    document_reference=self.number,
                    notes=f'Переміщення {self.number}: {self.employee_from_id.name} → {self.employee_to_id.name}',
                    company_id=balance.company_id.id,  # Використовуємо компанію з залишку
                    date=self.posting_datetime,
                )
                
                remaining_qty -= take_qty
        
        elif self.transfer_type == 'warehouse_employee':
            # Зі складу працівнику
            location_from_id = self.warehouse_from_id.lot_stock_id.id
            
            domain = [
                ('nomenclature_id', '=', line.nomenclature_id.id),
                ('location_type', '=', 'warehouse'),
                ('warehouse_id', '=', self.warehouse_from_id.id),
                ('company_id', 'in', self._get_child_companies(self.company_id)),
                ('qty_available', '>', 0)
            ]
            balances = self.env['stock.balance'].search(domain, order='batch_id ASC, id ASC')
            
            remaining_qty = line.qty
            for balance in balances:
                if remaining_qty <= 0:
                    break
                
                take_qty = min(balance.qty_available, remaining_qty)
                batch_id = balance.batch_id.id if balance.batch_id else None
                
                Movement.create_movement(
                    nomenclature_id=line.nomenclature_id.id,
                    qty=take_qty,
                    movement_type='transfer_out',
                    operation_type='transfer',
                    location_from_type='warehouse',
                    location_to_type='employee',
                    warehouse_from_id=self.warehouse_from_id.id,
                    employee_to_id=self.employee_to_id.id,
                    location_from_id=location_from_id,
                    batch_id=batch_id,
                    uom_id=line.selected_uom_id.id,
                    document_reference=self.number,
                    notes=f'Переміщення {self.number}: {self.warehouse_from_id.name} → {self.employee_to_id.name}',
                    company_id=balance.company_id.id,  # Використовуємо компанію з залишку
                    date=self.posting_datetime,
                )
                
                remaining_qty -= take_qty
        
        elif self.transfer_type == 'employee_warehouse':
            # Від працівника на склад
            location_to_id = self.warehouse_to_id.lot_stock_id.id
            
            domain = [
                ('nomenclature_id', '=', line.nomenclature_id.id),
                ('location_type', '=', 'employee'),
                ('employee_id', '=', self.employee_from_id.id),
                ('company_id', 'in', self._get_child_companies(self.company_id)),
                ('qty_available', '>', 0)
            ]
            balances = self.env['stock.balance'].search(domain, order='batch_id ASC, id ASC')
            
            remaining_qty = line.qty
            for balance in balances:
                if remaining_qty <= 0:
                    break
                
                take_qty = min(balance.qty_available, remaining_qty)
                batch_id = balance.batch_id.id if balance.batch_id else None
                
                Movement.create_movement(
                    nomenclature_id=line.nomenclature_id.id,
                    qty=take_qty,
                    movement_type='transfer_out',
                    operation_type='transfer',
                    location_from_type='employee',
                    location_to_type='warehouse',
                    employee_from_id=self.employee_from_id.id,
                    warehouse_to_id=self.warehouse_to_id.id,
                    location_to_id=location_to_id,
                    batch_id=batch_id,
                    uom_id=line.selected_uom_id.id,
                    document_reference=self.number,
                    notes=f'Переміщення {self.number}: {self.employee_from_id.name} → {self.warehouse_to_id.name}',
                    company_id=balance.company_id.id,  # Використовуємо компанію з залишку
                    date=self.posting_datetime,
                )
                
                remaining_qty -= take_qty



class StockReceiptIncoming(models.Model):
    """Інтеграція з прихідними накладними"""
    _inherit = 'stock.receipt.incoming'

    def _do_posting(self, posting_time, custom_datetime=None):
        """Розширюємо метод проведення для оновлення залишків"""
        _logger.info(f"Starting posting for receipt {self.number}")
        
        result = super()._do_posting(posting_time, custom_datetime)
        
        # Оновлюємо залишки для кожної позиції ПІСЛЯ проведення
        _logger.info(f"Creating balance movements for receipt {self.number}")
        for line in self.line_ids:
            try:
                self._create_balance_movement_for_line(line)
                _logger.info(f"Balance movement created for {line.nomenclature_id.name}")
            except Exception as e:
                _logger.error(f"Failed to create balance movement for {line.nomenclature_id.name}: {e}")
        
        return result

    def _create_balance_movement_for_line(self, line):
        """Створює рух залишків для позиції накладної"""
        if line.qty <= 0:
            _logger.warning(f"Skipping line with qty <= 0: {line.nomenclature_id.name}")
            return
        
        # Отримуємо локацію (якщо не вказана, використовуємо основну локацію складу)
        location = line.location_id or self.warehouse_id.lot_stock_id
        
        # Шукаємо партію для ВСІХ товарів, не тільки з серійними номерами
        batch = self.env['stock.batch'].search([
            ('source_document_type', '=', 'receipt'),
            ('source_document_number', '=', self.number),
            ('nomenclature_id', '=', line.nomenclature_id.id)
        ], limit=1)
        
        _logger.info(f"Found batch for {line.nomenclature_id.name}: {batch.batch_number if batch else 'None'}")
        
        try:
            # Створюємо рух залишків
            movement = self.env['stock.balance.movement'].create_movement(
                nomenclature_id=line.nomenclature_id.id,
                qty=line.qty,
                movement_type='in',
                operation_type='receipt',
                location_to_type='warehouse',
                warehouse_to_id=self.warehouse_id.id,
                location_to_id=location.id,
                batch_id=batch.id if batch else None,
                uom_id=line.selected_uom_id.id or line.product_uom_id.id,
                document_reference=self.number,
                notes=f'Прихідна накладна {self.number}',
                serial_numbers=line.serial_numbers if line.tracking_serial else None,
                company_id=self.company_id.id,
                date=self.posting_datetime,
            )
            
            _logger.info(f"Created balance movement: {movement.id}")
            
            self.message_post(
                body=_('Створено рух залишків для %s: +%s %s') % (
                    line.nomenclature_id.name, 
                    line.qty, 
                    (line.selected_uom_id or line.product_uom_id).name
                ),
                message_type='notification'
            )
            
        except Exception as e:
            _logger.error(f"Помилка створення руху залишків для {line.nomenclature_id.name}: {e}")
            self.message_post(
                body=_('Помилка оновлення залишків для %s: %s') % (line.nomenclature_id.name, str(e)),
                message_type='notification'
            )
            # Викидаємо помилку далі, щоб не приховувати проблему
            raise


class StockReceiptDisposal(models.Model):
    """Інтеграція з актами оприходування"""
    _inherit = 'stock.receipt.disposal'

    def _do_posting(self, posting_time, custom_datetime=None):
        """Розширюємо метод проведення для оновлення залишків"""
        _logger.info(f"Starting posting for disposal {self.number}")
        
        result = super()._do_posting(posting_time, custom_datetime)
        
        # Оновлюємо залишки для кожної позиції ПІСЛЯ проведення
        _logger.info(f"Creating balance movements for disposal {self.number}")
        for line in self.line_ids:
            try:
                self._create_balance_movement_for_line(line)
                _logger.info(f"Balance movement created for {line.nomenclature_id.name}")
            except Exception as e:
                _logger.error(f"Failed to create balance movement for {line.nomenclature_id.name}: {e}")
        
        return result

    def _create_balance_movement_for_line(self, line):
        """Створює рух залишків для позиції акта"""
        if line.qty <= 0:
            _logger.warning(f"Skipping line with qty <= 0: {line.nomenclature_id.name}")
            return
        
        # Отримуємо локацію (якщо не вказана, використовуємо основну локацію складу)
        location = line.location_id or self.warehouse_id.lot_stock_id
        
        # Шукаємо партію для цієї позиції
        batch = self.env['stock.batch'].search([
            ('source_document_type', '=', 'inventory'),
            ('source_document_number', '=', self.number),
            ('nomenclature_id', '=', line.nomenclature_id.id)
        ], limit=1)
        
        _logger.info(f"Found batch for {line.nomenclature_id.name}: {batch.batch_number if batch else 'None'}")
        
        try:
            # Створюємо рух залишків
            movement = self.env['stock.balance.movement'].create_movement(
                nomenclature_id=line.nomenclature_id.id,
                qty=line.qty,
                movement_type='in',
                operation_type='disposal',
                location_to_type='warehouse',
                warehouse_to_id=self.warehouse_id.id,
                location_to_id=location.id,
                batch_id=batch.id if batch else None,
                uom_id=line.selected_uom_id.id or line.product_uom_id.id,
                document_reference=self.number,
                notes=f'Акт оприходування {self.number}',
                serial_numbers=line.serial_numbers if line.tracking_serial else None,
                company_id=self.company_id.id,
                date=self.posting_datetime,
            )
            
            _logger.info(f"Created balance movement: {movement.id}")
            
            self.message_post(
                body=_('Створено рух залишків для %s: +%s %s') % (
                    line.nomenclature_id.name, 
                    line.qty, 
                    (line.selected_uom_id or line.product_uom_id).name
                ),
                message_type='notification'
            )
            
        except Exception as e:
            _logger.error(f"Помилка створення руху залишків для {line.nomenclature_id.name}: {e}")
            self.message_post(
                body=_('Помилка оновлення залишків для %s: %s') % (line.nomenclature_id.name, str(e)),
                message_type='notification'
            )
            # Викидаємо помилку далі, щоб не приховувати проблему  
            raise

class StockReceiptIncoming(models.Model):
    _inherit = 'stock.receipt.incoming'

    def action_done(self):
        result = super().action_done()
        
        for line in self.line_ids:
            if line.qty > 0:
                Movement = self.env['stock.balance.movement']
                serial_numbers = line.serial_numbers if line.tracking_serial else None
                
                Movement.create_movement(
                    nomenclature_id=line.nomenclature_id.id,
                    movement_type='in',
                    operation_type='receipt',
                    qty=line.qty,
                    uom_id=line.selected_uom_id.id,
                    date=self.posting_datetime or fields.Datetime.now(),
                    document_reference=f'Прихідна накладна {self.number}',
                    serial_numbers=serial_numbers,
                    company_id=self.company_id.id,
                    location_to_type='warehouse',
                    warehouse_to_id=self.warehouse_id.id,
                    location_to_id=self.warehouse_id.lot_stock_id.id,
                )
        return result

# Інтеграція для актів оприходування
class StockReceiptDisposal(models.Model):
    _inherit = 'stock.receipt.disposal'

    def action_done(self):
        result = super().action_done()
        
        for line in self.line_ids:
            if line.qty > 0:
                Movement = self.env['stock.balance.movement']
                serial_numbers = line.serial_numbers if line.tracking_serial else None
                
                Movement.create_movement(
                    nomenclature_id=line.nomenclature_id.id,
                    movement_type='in',
                    operation_type='disposal',
                    qty=line.qty,
                    uom_id=line.selected_uom_id.id,
                    date=self.posting_datetime or fields.Datetime.now(),
                    document_reference=f'Акт оприходування {self.number}',
                    serial_numbers=serial_numbers,
                    company_id=self.company_id.id,
                    location_to_type='warehouse',
                    warehouse_to_id=self.warehouse_id.id,
                    location_to_id=self.warehouse_id.lot_stock_id.id,
                )
        return result