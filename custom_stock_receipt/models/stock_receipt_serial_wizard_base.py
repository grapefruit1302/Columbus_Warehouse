from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from .utils import parse_serial_numbers, format_serial_numbers, validate_serial_numbers
import logging

_logger = logging.getLogger(__name__)


class StockReceiptSerialWizardBase(models.AbstractModel):
    """Базовий клас для wizard серійних номерів"""
    _name = 'stock.receipt.serial.wizard.base'
    _description = 'Базовий wizard для серійних номерів'

    warning_message = fields.Text('Попередження', readonly=True)
    selected_product_name = fields.Char('Назва товару', readonly=True)
    selected_qty = fields.Float('Кількість', readonly=True)
    current_serial_count = fields.Integer('Поточна кількість S/N', compute='_compute_current_serial_count')
    serial_line_ids = fields.One2many('stock.receipt.serial.wizard.line.base', 'wizard_id', 'Серійні номери')

    @api.depends('serial_line_ids')
    def _compute_current_serial_count(self):
        for wizard in self:
            wizard.current_serial_count = len([line for line in wizard.serial_line_ids if line.serial_number])
    
    @api.constrains('serial_line_ids', 'selected_qty')
    def _check_serial_count_limit(self):
        """Перевіряє, що кількість серійних номерів не перевищує кількість в документі"""
        for wizard in self:
            if wizard.selected_qty and wizard.current_serial_count > wizard.selected_qty:
                raise ValidationError(
                    _('Кількість серійних номерів (%d) не може перевищувати кількість в документі (%d)') % 
                    (wizard.current_serial_count, int(wizard.selected_qty))
                )

    # Абстрактні методи
    def _get_document_field_name(self):
        """Повертає назву поля документа"""
        raise NotImplementedError()

    def _get_line_field_name(self):
        """Повертає назву поля позиції"""
        raise NotImplementedError()

    def _get_document_model(self):
        """Повертає модель документа"""
        raise NotImplementedError()

    def _get_line_model(self):
        """Повертає модель позиції документа"""
        raise NotImplementedError()

    def _get_serial_line_model(self):
        """Повертає модель для рядків серійних номерів"""
        raise NotImplementedError()

    def _get_balance_operation_type(self):
        """Повертає тип операції для балансу"""
        raise NotImplementedError()

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        line_field = self._get_line_field_name()
        line_id = self.env.context.get(f'default_{line_field}')
        
        if line_id:
            line_model = self._get_line_model()
            line = self.env[line_model].browse(line_id)
            document_field = self._get_document_field_name()
            
            res[document_field] = getattr(line, document_field).id
            res[line_field] = line_id
            res['selected_product_name'] = line.nomenclature_id.name
            res['selected_qty'] = line.qty
            
            if line.serial_numbers:
                existing_serials = parse_serial_numbers(line.serial_numbers)
                res['serial_line_ids'] = [(0, 0, {'serial_number': serial}) for serial in existing_serials]
        
        return res

    def action_save_and_close(self):
        """Зберігає серійні номери та оновлює залишки"""
        self.ensure_one()
        validation_result = self._validate_serial_numbers()
        
        if isinstance(validation_result, dict) and validation_result.get('type') == 'ir.actions.act_window':
            return validation_result
        
        # Зберігаємо серійні номери в рядку документа
        serials = [line.serial_number for line in self.serial_line_ids if line.serial_number]
        serial_numbers_text = format_serial_numbers(serials)
        
        line_field = self._get_line_field_name()
        selected_line = getattr(self, line_field)
        
        _logger.info(f"🔧 Saving serial numbers to line: '{serial_numbers_text}'")
        selected_line.serial_numbers = serial_numbers_text
        
        # Оновлення серійних номерів в залишках
        self._update_balance_serial_numbers(serial_numbers_text)
        
        return {'type': 'ir.actions.act_window_close'}

    def _update_balance_serial_numbers(self, serial_numbers_text):
        """Оновлює серійні номери в відповідних залишках"""
        line_field = self._get_line_field_name()
        document_field = self._get_document_field_name()
        selected_line = getattr(self, line_field)
        document = getattr(self, document_field)
        
        _logger.info(f"🔄 Updating balance serial numbers for document {document.number}")
        
        # Знаходимо всі залишки створені з цього документа
        balances = self.env['stock.balance'].search([
            ('nomenclature_id', '=', selected_line.nomenclature_id.id),
            ('location_type', '=', 'warehouse'),
            ('warehouse_id', '=', document.warehouse_id.id),
        ])
        
        _logger.info(f"📊 Found {len(balances)} balance records")
        
        operation_type = self._get_balance_operation_type()
        
        for balance in balances:
            # Знаходимо відповідний рух залишків
            movement = self.env['stock.balance.movement'].search([
                ('nomenclature_id', '=', selected_line.nomenclature_id.id),
                ('document_reference', '=', document.number),
                ('operation_type', '=', operation_type),
            ], limit=1)
            
            if movement:
                _logger.info(f"🎯 Updating balance ID: {balance.id}")
                
                # Оновлюємо серійні номери в залишках
                balance.write({
                    'serial_numbers': serial_numbers_text,
                    'last_update': fields.Datetime.now(),
                })
                
                # Також оновлюємо в русі залишків
                movement.write({
                    'serial_numbers': serial_numbers_text,
                })
                
                _logger.info(f"✅ Balance updated successfully!")
                
                # Надсилаємо повідомлення в чат документа
                document.message_post(
                    body=_('🔢 Оновлено серійні номери для %s: %s') % (
                        selected_line.nomenclature_id.name,
                        serial_numbers_text.replace('\n', ', ')
                    ),
                    message_type='notification'
                )
                
                return True
        
        _logger.warning(f"⚠️ No balance found to update for {selected_line.nomenclature_id.name}")
        return False

    def _validate_serial_numbers(self):
        """Валідація серійних номерів"""
        line_field = self._get_line_field_name()
        selected_line = getattr(self, line_field)
        
        serials = [line.serial_number for line in self.serial_line_ids if line.serial_number]
        
        if not serials:
            return True
        
        # Використовуємо загальну валідацію з utils
        is_valid, errors = validate_serial_numbers(
            self.env, 
            serials, 
            selected_line.nomenclature_id.id
        )
        
        if not is_valid:
            raise ValidationError('\n'.join(errors))
        
        return True

    def remove_duplicates(self):
        """Видаляє дублікати серійних номерів"""
        serials = []
        unique_serials = []
        
        for line in self.serial_line_ids:
            if line.serial_number:
                if line.serial_number not in serials:
                    serials.append(line.serial_number)
                    unique_serials.append(line.serial_number)
        
        # Очищаємо і створюємо нові записи без дублікатів
        self.serial_line_ids = [(5, 0, 0)]  # Видаляємо всі існуючі записи
        serial_lines = [(0, 0, {'serial_number': serial}) for serial in unique_serials]
        self.serial_line_ids = serial_lines
        
        duplicates_removed = len(serials) - len(unique_serials)
        
        # Показуємо повідомлення про результат
        if duplicates_removed > 0:
            message = _('Видалено %d дублікатів серійних номерів') % duplicates_removed
        else:
            message = _('Дублікати серійних номерів не знайдено')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Результат видалення дублікатів'),
                'message': message,
                'type': 'success' if duplicates_removed > 0 else 'info',
                'sticky': False,
            }
        }

    def action_load_from_file(self):
        """Завантаження серійних номерів з файлу"""
        raise UserError(_('Функція завантаження з файлу поки не реалізована'))

    def action_generate_serials(self):
        """Генерація серійних номерів"""
        raise UserError(_('Функція генерації серійних номерів поки не реалізована'))

    def action_clear_all(self):
        """Очищення всіх серійних номерів"""
        self.serial_line_ids = [(5, 0, 0)]
        return True

    def action_add_serial_line(self):
        """Додавання нового рядка серійного номера"""
        if self.selected_qty and self.current_serial_count >= self.selected_qty:
            raise UserError(
                _('Не можна додати більше серійних номерів. Досягнуто максимум: %d') % 
                int(self.selected_qty)
            )
        self.serial_line_ids = [(0, 0, {'serial_number': ''})]
        return True


class StockReceiptSerialWizardLineBase(models.AbstractModel):
    """Базовий клас для рядків серійних номерів"""
    _name = 'stock.receipt.serial.wizard.line.base'
    _description = 'Базовий клас для рядків серійних номерів'

    wizard_id = fields.Many2one('stock.receipt.serial.wizard.base', 'Wizard', required=True, ondelete='cascade')
    serial_number = fields.Char('Серійний номер', required=True)
    is_duplicate = fields.Boolean('Дублікат', compute='_compute_is_duplicate')
    is_existing = fields.Boolean('Існує в системі', compute='_compute_is_existing')

    @api.depends('serial_number', 'wizard_id.serial_line_ids.serial_number')
    def _compute_is_duplicate(self):
        """Перевіряє, чи є серійний номер дублікатом в межах wizard"""
        for line in self:
            if line.serial_number:
                other_lines = line.wizard_id.serial_line_ids.filtered(lambda l: l.id != line.id)
                line.is_duplicate = line.serial_number in other_lines.mapped('serial_number')
            else:
                line.is_duplicate = False

    @api.depends('serial_number')
    def _compute_is_existing(self):
        """Перевіряє, чи існує серійний номер в системі"""
        for line in self:
            if line.serial_number:
                existing = self.env['stock.balance'].search([
                    ('serial_numbers', 'ilike', line.serial_number)
                ], limit=1)
                line.is_existing = bool(existing)
            else:
                line.is_existing = False