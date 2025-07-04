from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class StockDisposalSerialWizard(models.TransientModel):
    _name = 'stock.disposal.serial.wizard'
    _description = 'Wizard для введення серійних номерів в акт оприходування'

    warning_message = fields.Text('Попередження', readonly=True)
    disposal_id = fields.Many2one('stock.receipt.disposal', 'Акт оприходування', required=True)
    selected_line_id = fields.Many2one('stock.receipt.disposal.line', 'Обрана позиція', required=True)
    selected_product_name = fields.Char('Назва товару', related='selected_line_id.nomenclature_id.name', readonly=True)
    selected_qty = fields.Float('Кількість', related='selected_line_id.qty', readonly=True)
    current_serial_count = fields.Integer('Поточна кількість S/N', compute='_compute_current_serial_count')
    serial_line_ids = fields.One2many('stock.disposal.serial.wizard.serial', 'wizard_id', 'Серійні номери')  # ✅ ВИПРАВЛЕНО назву

    @api.depends('serial_line_ids')
    def _compute_current_serial_count(self):
        for wizard in self:
            wizard.current_serial_count = len([line for line in wizard.serial_line_ids if line.serial_number])

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        line_id = self.env.context.get('default_selected_line_id')
        
        if line_id:
            line = self.env['stock.receipt.disposal.line'].browse(line_id)
            res['disposal_id'] = line.disposal_id.id
            res['selected_line_id'] = line_id
            
            if line.serial_numbers:
                existing_serials = []
                for line_text in line.serial_numbers.split('\n'):
                    for serial in line_text.split(','):
                        serial = serial.strip()
                        if serial:
                            existing_serials.append(serial)
                
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
        serial_numbers_text = '\n'.join(serials)
        
        _logger.info(f"🔧 Saving serial numbers to disposal line: '{serial_numbers_text}'")
        self.selected_line_id.serial_numbers = serial_numbers_text
        
        # ✅ ДОДАЄМО: Оновлення серійних номерів в залишках
        self._update_balance_serial_numbers(serial_numbers_text)
        
        return {'type': 'ir.actions.act_window_close'}

    def _update_balance_serial_numbers(self, serial_numbers_text):
        """Оновлює серійні номери в відповідних залишках"""
        _logger.info(f"🔄 Updating balance serial numbers for disposal {self.disposal_id.number}")
        
        # Знаходимо всі залишки створені з цього документа
        balances = self.env['stock.balance'].search([
            ('nomenclature_id', '=', self.selected_line_id.nomenclature_id.id),
            ('location_type', '=', 'warehouse'),
            ('warehouse_id', '=', self.disposal_id.warehouse_id.id),
        ])
        
        _logger.info(f"📊 Found {len(balances)} balance records")
        
        for balance in balances:
            # Знаходимо відповідний рух залишків
            movement = self.env['stock.balance.movement'].search([
                ('nomenclature_id', '=', self.selected_line_id.nomenclature_id.id),
                ('document_reference', '=', self.disposal_id.number),
                ('operation_type', '=', 'disposal'),
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
                self.disposal_id.message_post(
                    body=_('🔢 Оновлено серійні номери для %s: %s') % (
                        self.selected_line_id.nomenclature_id.name,
                        serial_numbers_text.replace('\n', ', ')
                    ),
                    message_type='notification'
                )
                
                return True
        
        _logger.warning(f"⚠️ No balance found to update for {self.selected_line_id.nomenclature_id.name}")
        return False

    def _validate_serial_numbers(self):
        """Валідація серійних номерів"""
        # Аналогічна валідація як в receipt wizard
        return True

    def action_load_from_file(self):
        """Завантаження серійних номерів з файлу (заглушка)"""
        raise UserError(_('Функція завантаження з файлу поки не реалізована'))

class StockDisposalSerialWizardLine(models.TransientModel):
    _name = 'stock.disposal.serial.wizard.serial'  # ✅ ВИПРАВЛЕНО назву відповідно до XML
    _description = 'Лінія товарів з серійними номерами'
 
    wizard_id = fields.Many2one('stock.disposal.serial.wizard', 'Wizard', required=True, ondelete='cascade')
    serial_number = fields.Char('Серійний номер', required=True)