# 1. Розширення моделі stock.receipt.incoming для інтеграції з залишками
# custom_stock_receipt/models/stock_receipt_integration.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class StockReceiptIncoming(models.Model):
    _inherit = 'stock.receipt.incoming'

    def action_done(self):
        """Розширюємо метод проведення для створення рухів залишків"""
        # Спочатку стандартне проведення
        result = super().action_done()
        
        # Потім створюємо рухи залишків якщо модуль встановлений
        if 'stock.balance.movement' in self.env:
            for line in self.line_ids:
                self._create_balance_movement_for_line(line)
        
        return result

    def _create_balance_movement_for_line(self, line):
        """Створює рух залишків для позиції прихідної накладної"""
        if line.qty <= 0:
            return
        
        Movement = self.env['stock.balance.movement']
        
        # Збираємо серійні номери з рядка
        serial_numbers = None
        if line.tracking_serial and line.serial_numbers:
            serial_numbers = line.serial_numbers
        
        # Створюємо рух надходження
        movement_vals = {
            'nomenclature_id': line.nomenclature_id.id,
            'movement_type': 'in',
            'operation_type': 'receipt',
            'qty': line.qty,
            'uom_id': line.selected_uom_id.id if line.selected_uom_id else line.nomenclature_id.base_uom_id.id,
            'date': self.posting_datetime or fields.Datetime.now(),
            'document_reference': f'Прихідна накладна {self.number}',
            'notes': f'Надходження від {self.supplier_id.name}',
            'serial_numbers': serial_numbers,
            'company_id': self.company_id.id,
            'location_to_type': 'warehouse',
            'warehouse_to_id': self.warehouse_id.id,
            'location_to_id': line.location_id.id if line.location_id else self.warehouse_id.lot_stock_id.id,
        }
        
        try:
            Movement.create_movement(**movement_vals)
            _logger.info(f"Створено рух залишків для {line.nomenclature_id.name} з S/N")
        except Exception as e:
            _logger.error(f"Помилка створення руху залишків: {e}")
            self.message_post(
                body=_('Помилка оновлення залишків для %s: %s') % (line.nomenclature_id.name, str(e)),
                message_type='notification'
            )


class StockReceiptDisposal(models.Model):
    _inherit = 'stock.receipt.disposal'

    def action_done(self):
        """Розширюємо метод проведення для створення рухів залишків"""
        # Спочатку стандартне проведення
        result = super().action_done()
        
        # Потім створюємо рухи залишків якщо модуль встановлений
        if 'stock.balance.movement' in self.env:
            for line in self.line_ids:
                self._create_balance_movement_for_line(line)
        
        return result

    def _create_balance_movement_for_line(self, line):
        """Створює рух залишків для позиції акта оприходування"""
        if line.qty <= 0:
            return
        
        Movement = self.env['stock.balance.movement']
        
        # Збираємо серійні номери з рядка
        serial_numbers = None
        if line.tracking_serial and line.serial_numbers:
            serial_numbers = line.serial_numbers
        
        # Створюємо рух надходження
        movement_vals = {
            'nomenclature_id': line.nomenclature_id.id,
            'movement_type': 'in',
            'operation_type': 'disposal',
            'qty': line.qty,
            'uom_id': line.selected_uom_id.id if line.selected_uom_id else line.nomenclature_id.base_uom_id.id,
            'date': self.posting_datetime or fields.Datetime.now(),
            'document_reference': f'Акт оприходування {self.number}',
            'notes': 'Оприходування без постачальника',
            'serial_numbers': serial_numbers,
            'company_id': self.company_id.id,
            'location_to_type': 'warehouse',
            'warehouse_to_id': self.warehouse_id.id,
            'location_to_id': line.location_id.id if line.location_id else self.warehouse_id.lot_stock_id.id,
        }
        
        try:
            Movement.create_movement(**movement_vals)
            _logger.info(f"Створено рух залишків для {line.nomenclature_id.name} з S/N")
        except Exception as e:
            _logger.error(f"Помилка створення руху залишків: {e}")
            self.message_post(
                body=_('Помилка оновлення залишків для %s: %s') % (line.nomenclature_id.name, str(e)),
                message_type='notification'
            )


# 2. Розширення моделі stock.balance для роботи з серійними номерами
# stock_balance_management/models/stock_balance_serial.py

class StockBalance(models.Model):
    _inherit = 'stock.balance'

    # Додаємо методи для роботи з серійними номерами
    def get_serial_numbers_list(self):
        """Повертає список серійних номерів"""
        self.ensure_one()
        if not self.serial_numbers:
            return []
        
        # Розділяємо серійні номери по комі або новому рядку
        serials = []
        for line in self.serial_numbers.split('\n'):
            for serial in line.split(','):
                serial = serial.strip()
                if serial:
                    serials.append(serial)
        return serials

    def add_serial_numbers(self, new_serials):
        """Додає нові серійні номери до залишку"""
        self.ensure_one()
        
        if not new_serials:
            return
        
        current_serials = self.get_serial_numbers_list()
        
        # Перевіряємо на дублікати
        for serial in new_serials:
            if serial not in current_serials:
                current_serials.append(serial)
        
        # Оновлюємо поле
        self.serial_numbers = '\n'.join(current_serials)

    def remove_serial_numbers(self, serials_to_remove):
        """Видаляє серійні номери із залишку"""
        self.ensure_one()
        
        if not serials_to_remove:
            return
        
        current_serials = self.get_serial_numbers_list()
        
        # Видаляємо вказані серійні номери
        for serial in serials_to_remove:
            if serial in current_serials:
                current_serials.remove(serial)
        
        # Оновлюємо поле
        self.serial_numbers = '\n'.join(current_serials) if current_serials else False

    @api.model
    def update_balance_with_serials(self, nomenclature_id, qty_change, serial_numbers=None, **kwargs):
        """Оновлює баланс з урахуванням серійних номерів"""
        
        # Знаходимо або створюємо запис залишку
        balance = self.update_balance(nomenclature_id, qty_change, **kwargs)
        
        # Обробляємо серійні номери якщо вони є
        if serial_numbers and balance:
            serials_list = []
            
            # Парсимо серійні номери
            for line in serial_numbers.split('\n'):
                for serial in line.split(','):
                    serial = serial.strip()
                    if serial:
                        serials_list.append(serial)
            
            if serials_list:
                if qty_change > 0:
                    # Додаємо серійні номери при надходженні
                    balance.add_serial_numbers(serials_list)
                else:
                    # Видаляємо серійні номери при списанні
                    balance.remove_serial_numbers(serials_list)
        
        return balance


# 3. Розширення представлення залишків для відображення серійних номерів
# stock_balance_management/views/stock_balance_serial_views.xml

"""
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data>
        <!-- Додаємо поле серійних номерів до форми залишків -->
        <record id="view_stock_balance_form_serial" model="ir.ui.view">
            <field name="name">stock.balance.form.serial</field>
            <field name="model">stock.balance</field>
            <field name="inherit_id" ref="stock_balance_management.view_stock_balance_form"/>
            <field name="arch" type="xml">
                <notebook position="inside">
                    <page string="Серійні номери" invisible="serial_numbers == False">
                        <group>
                            <field name="serial_numbers" widget="text" readonly="1" 
                                   help="Серійні номери товарів у цьому залишку"/>
                        </group>
                        
                        <div class="alert alert-info" role="alert" invisible="serial_numbers == False">
                            <strong>Серійні номери:</strong><br/>
                            <field name="serial_numbers" widget="text" readonly="1" nolabel="1"/>
                        </div>
                    </page>
                </notebook>
            </field>
        </record>

        <!-- Додаємо колонку серійних номерів до списку залишків -->
        <record id="view_stock_balance_list_serial" model="ir.ui.view">
            <field name="name">stock.balance.list.serial</field>
            <field name="model">stock.balance</field>
            <field name="inherit_id" ref="stock_balance_management.view_stock_balance_list"/>
            <field name="arch" type="xml">
                <field name="qty_available" position="after">
                    <field name="serial_numbers" string="S/N" optional="hide" 
                           help="Серійні номери"/>
                </field>
            </field>
        </record>

        <!-- Фільтр для товарів з серійними номерами -->
        <record id="view_stock_balance_search_serial" model="ir.ui.view">
            <field name="name">stock.balance.search.serial</field>
            <field name="model">stock.balance</field>
            <field name="inherit_id" ref="stock_balance_management.stock_balance_search_view"/>
            <field name="arch" type="xml">
                <filter name="with_qty" position="after">
                    <filter string="З серійними номерами" name="with_serials" 
                            domain="[('serial_numbers', '!=', False)]"/>
                </filter>
            </field>
        </record>
    </data>
</odoo>
"""


# 4. Метод для перегляду серійних номерів у залишках
# stock_balance_management/models/stock_balance_serial_wizard.py

class StockBalanceSerialWizard(models.TransientModel):
    _name = 'stock.balance.serial.wizard'
    _description = 'Перегляд серійних номерів у залишках'

    balance_id = fields.Many2one('stock.balance', 'Залишок', required=True)
    nomenclature_name = fields.Char('Товар', related='balance_id.nomenclature_id.name', readonly=True)
    location_info = fields.Char('Локація', compute='_compute_location_info', readonly=True)
    qty_available = fields.Float('Доступна кількість', related='balance_id.qty_available', readonly=True)
    serial_line_ids = fields.One2many('stock.balance.serial.wizard.line', 'wizard_id', 'Серійні номери')

    @api.depends('balance_id')
    def _compute_location_info(self):
        for wizard in self:
            if wizard.balance_id.location_type == 'warehouse':
                wizard.location_info = f"Склад: {wizard.balance_id.warehouse_id.name}"
            else:
                wizard.location_info = f"Працівник: {wizard.balance_id.employee_id.name}"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        balance_id = self.env.context.get('active_id')
        
        if balance_id:
            balance = self.env['stock.balance'].browse(balance_id)
            res['balance_id'] = balance_id
            
            # Завантажуємо серійні номери
            serials = balance.get_serial_numbers_list()
            res['serial_line_ids'] = [(0, 0, {'serial_number': serial}) for serial in serials]
        
        return res


class StockBalanceSerialWizardLine(models.TransientModel):
    _name = 'stock.balance.serial.wizard.line'
    _description = 'Рядок серійного номера'

    wizard_id = fields.Many2one('stock.balance.serial.wizard', 'Wizard', required=True, ondelete='cascade')
    serial_number = fields.Char('Серійний номер', required=True)


# 5. Додаткові методи для звітності по серійних номерах
# stock_balance_management/reports/stock_serial_report.py

class StockSerialReport(models.Model):
    _name = 'stock.serial.report'
    _description = 'Звіт по серійних номерах'
    _auto = False

    nomenclature_id = fields.Many2one('product.nomenclature', 'Номенклатура')
    nomenclature_name = fields.Char('Назва товару')
    serial_number = fields.Char('Серійний номер')
    location_type = fields.Selection([
        ('warehouse', 'Склад'),
        ('employee', 'Працівник'),
    ], 'Тип локації')
    warehouse_name = fields.Char('Склад')
    employee_name = fields.Char('Працівник')
    company_id = fields.Many2one('res.company', 'Компанія')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT 
                    row_number() OVER () AS id,
                    sb.nomenclature_id,
                    pn.name AS nomenclature_name,
                    regexp_split_to_table(sb.serial_numbers, E'[,\\n]') AS serial_number,
                    sb.location_type,
                    sw.name AS warehouse_name,
                    he.name AS employee_name,
                    sb.company_id
                FROM stock_balance sb
                LEFT JOIN product_nomenclature pn ON pn.id = sb.nomenclature_id
                LEFT JOIN stock_warehouse sw ON sw.id = sb.warehouse_id
                LEFT JOIN hr_employee he ON he.id = sb.employee_id
                WHERE sb.serial_numbers IS NOT NULL
                AND sb.serial_numbers != ''
                AND sb.qty_available > 0
            )
        """ % self._table)