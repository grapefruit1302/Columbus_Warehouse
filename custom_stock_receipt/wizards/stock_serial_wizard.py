from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class StockSerialWizard(models.TransientModel):
    """Універсальний wizard для введення серійних номерів"""
    _name = 'stock.serial.wizard'
    _description = 'Wizard для введення серійних номерів'

    document_model = fields.Char(
        'Модель документу',
        required=True,
        help='Назва моделі документу (наприклад: stock.receipt.incoming)'
    )
    
    document_id = fields.Integer(
        'ID документу',
        required=True,
        help='ID документу для якого вводяться серійні номери'
    )
    
    line_id = fields.Integer(
        'ID позиції',
        help='ID конкретної позиції документу (опціонально)'
    )
    
    nomenclature_id = fields.Many2one(
        'product.nomenclature',
        'Товар',
        readonly=True,
        help='Товар для якого вводяться серійні номери'
    )
    
    qty = fields.Float(
        'Кількість',
        readonly=True,
        help='Кількість товару в позиції'
    )
    
    serial_numbers = fields.Text(
        'Серійні номери',
        required=True,
        help='Введіть серійні номери, розділені комою або новим рядком'
    )
    
    current_serials = fields.Text(
        'Поточні серійні номери',
        readonly=True,
        help='Серійні номери які вже введені для цієї позиції'
    )
    
    serial_count = fields.Integer(
        'Кількість введених S/N',
        compute='_compute_serial_count',
        help='Кількість введених серійних номерів'
    )
    
    validation_message = fields.Html(
        'Повідомлення валідації',
        compute='_compute_validation_message',
        help='Результат валідації введених серійних номерів'
    )
    
    @api.depends('serial_numbers')
    def _compute_serial_count(self):
        """Підраховує кількість введених серійних номерів"""
        for wizard in self:
            if wizard.serial_numbers:
                serials = self.env['stock.serial.number']._parse_serial_text(wizard.serial_numbers)
                wizard.serial_count = len(serials)
            else:
                wizard.serial_count = 0
    
    @api.depends('serial_numbers', 'qty', 'nomenclature_id')
    def _compute_validation_message(self):
        """Обчислює повідомлення валідації"""
        for wizard in self:
            if not wizard.serial_numbers:
                wizard.validation_message = '<span class="text-muted">Введіть серійні номери</span>'
                continue
            
            try:
                serials = self.env['stock.serial.number']._parse_serial_text(wizard.serial_numbers)
                messages = []
                
                if len(serials) != int(wizard.qty):
                    messages.append(
                        f'<span class="text-warning">⚠️ Кількість серійних номерів ({len(serials)}) '
                        f'не відповідає кількості товару ({int(wizard.qty)})</span>'
                    )
                else:
                    messages.append(
                        f'<span class="text-success">✅ Кількість серійних номерів відповідає кількості товару</span>'
                    )
                
                if len(serials) != len(set(serials)):
                    duplicates = [serial for serial in serials if serials.count(serial) > 1]
                    messages.append(
                        f'<span class="text-danger">❌ Знайдено дублікати: {", ".join(set(duplicates))}</span>'
                    )
                
                # Перевірка на існування в системі
                if wizard.nomenclature_id:
                    existing_serials = []
                    for serial in serials:
                        existing = wizard.env['stock.serial.number'].search([
                            ('serial_number', '=', serial),
                            ('nomenclature_id', '=', wizard.nomenclature_id.id),
                            ('is_active', '=', True)
                        ])
                        if existing:
                            existing_serials.append(f"{serial} ({existing.display_location})")
                    
                    if existing_serials:
                        messages.append(
                            f'<span class="text-danger">❌ Серійні номери вже існують в системі:<br/>'
                            f'{"<br/>".join(existing_serials)}</span>'
                        )
                
                wizard.validation_message = '<br/>'.join(messages) if messages else '<span class="text-success">✅ Всі перевірки пройдені</span>'
                
            except Exception as e:
                wizard.validation_message = f'<span class="text-danger">❌ Помилка валідації: {str(e)}</span>'
    
    @api.model
    def default_get(self, fields_list):
        """Заповнює значення за замовчуванням"""
        res = super().default_get(fields_list)
        
        document_model = self.env.context.get('default_document_model')
        document_id = self.env.context.get('default_document_id')
        line_id = self.env.context.get('default_line_id')
        
        if document_model and document_id:
            res['document_model'] = document_model
            res['document_id'] = document_id
            
            try:
                document = self.env[document_model].browse(document_id)
                
                if line_id:
                    res['line_id'] = line_id
                    line = document.line_ids.filtered(lambda l: l.id == line_id)
                    if line:
                        res['nomenclature_id'] = line.nomenclature_id.id
                        res['qty'] = line.qty
                        res['current_serials'] = line.serial_numbers or ''
                        res['serial_numbers'] = line.serial_numbers or ''
                
            except Exception as e:
                _logger.error(f"Помилка отримання даних документу: {e}")
        
        return res
    
    def action_save_serials(self):
        """Зберігає серійні номери"""
        self.ensure_one()
        
        self._validate_serial_numbers()
        
        try:
            document = self.env[self.document_model].browse(self.document_id)
            
            if self.line_id:
                line = document.line_ids.filtered(lambda l: l.id == self.line_id)
                if not line:
                    raise UserError(_('Позицію не знайдено!'))
                
                line.serial_numbers = self.serial_numbers
                
                if document.state == 'posted':
                    self._create_centralized_serials(document, line)
                
                self.env.cr.commit()
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Успіх'),
                        'message': _('Серійні номери збережено для товару: %s') % line.nomenclature_id.name,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return self._show_bulk_input_wizard(document)
                
        except Exception as e:
            _logger.error(f"Помилка збереження серійних номерів: {e}")
            raise UserError(_('Помилка збереження серійних номерів: %s') % str(e))
    
    def _validate_serial_numbers(self):
        """Валідує введені серійні номери"""
        if not self.serial_numbers:
            raise UserError(_('Введіть серійні номери!'))
        
        serials = self.env['stock.serial.number']._parse_serial_text(self.serial_numbers)
        
        if len(serials) != int(self.qty):
            raise UserError(
                _('Кількість серійних номерів (%d) не відповідає кількості товару (%d)') % 
                (len(serials), self.qty)
            )
        
        # Перевірка на дублікати
        if len(serials) != len(set(serials)):
            duplicates = [serial for serial in serials if serials.count(serial) > 1]
            raise UserError(
                _('Знайдено дублікати серійних номерів: %s') % ', '.join(set(duplicates))
            )
        
        # Перевірка на існування в системі
        if self.nomenclature_id:
            for serial in serials:
                existing = self.env['stock.serial.number'].search([
                    ('serial_number', '=', serial),
                    ('nomenclature_id', '=', self.nomenclature_id.id),
                    ('is_active', '=', True)
                ])
                if existing:
                    raise UserError(
                        _('Серійний номер "%s" вже існує в системі!\nПоточна локація: %s') % 
                        (serial, existing.display_location)
                    )
    
    def _create_centralized_serials(self, document, line):
        """Створює записи в централізованій таблиці серійних номерів"""
        document_type = self._get_document_type(document)
        
        location_type, warehouse_id, employee_id = self._get_location_info(document)
        
        self.env['stock.serial.number'].create_from_text(
            serial_text=self.serial_numbers,
            nomenclature_id=line.nomenclature_id.id,
            document_type=document_type,
            document_id=document.id,
            document_reference=document.number,
            location_type=location_type,
            warehouse_id=warehouse_id,
            employee_id=employee_id,
            company_id=document.company_id.id,
            notes=f"Створено через wizard з документа {document.number}"
        )
    
    def _get_document_type(self, document):
        """Визначає тип документа для серійних номерів"""
        if 'incoming' in document._name:
            return 'incoming'
        elif 'disposal' in document._name:
            return 'disposal'
        elif 'return' in document._name:
            return 'return'
        else:
            return 'incoming'  # За замовчуванням
    
    def _get_location_info(self, document):
        """Визначає інформацію про локацію"""
        return ('warehouse', document.warehouse_id.id if document.warehouse_id else None, None)
    
    def _show_bulk_input_wizard(self, document):
        """Показує wizard для масового введення серійних номерів"""
        serial_lines = document.line_ids.filtered('nomenclature_id.tracking_serial')
        
        if not serial_lines:
            raise UserError(_('У документі немає товарів з обліком по серійних номерах!'))
        
        return {
            'name': _('Масове введення серійних номерів'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.serial.bulk.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_model': document._name,
                'default_document_id': document.id,
                'default_line_ids': [(6, 0, serial_lines.ids)],
            }
        }
    
    def action_cancel(self):
        """Скасовує wizard"""
        return {'type': 'ir.actions.act_window_close'}
    
    def action_preview_serials(self):
        """Показує попередній перегляд серійних номерів"""
        if not self.serial_numbers:
            raise UserError(_('Введіть серійні номери для попереднього перегляду!'))
        
        serials = self.env['stock.serial.number']._parse_serial_text(self.serial_numbers)
        
        message = _('Буде створено %d серійних номерів:\n\n%s') % (
            len(serials),
            '\n'.join(f'• {serial}' for serial in serials)
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Попередній перегляд'),
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }


class StockSerialBulkWizard(models.TransientModel):
    """Wizard для масового введення серійних номерів"""
    _name = 'stock.serial.bulk.wizard'
    _description = 'Wizard для масового введення серійних номерів'

    document_model = fields.Char('Модель документу', required=True)
    document_id = fields.Integer('ID документу', required=True)
    
    line_ids = fields.One2many(
        'stock.serial.bulk.line',
        'wizard_id',
        'Позиції з серійними номерами'
    )
    
    @api.model
    def default_get(self, fields_list):
        """Заповнює позиції за замовчуванням"""
        res = super().default_get(fields_list)
        
        document_model = self.env.context.get('default_document_model')
        document_id = self.env.context.get('default_document_id')
        line_ids = self.env.context.get('default_line_ids', [])
        
        if document_model and document_id and line_ids:
            res['document_model'] = document_model
            res['document_id'] = document_id
            
            document = self.env[document_model].browse(document_id)
            wizard_lines = []
            
            for line_id in line_ids[0][2]:  # Розпаковуємо (6, 0, [ids])
                line = document.line_ids.filtered(lambda l: l.id == line_id)
                if line and line.nomenclature_id.tracking_serial:
                    wizard_lines.append((0, 0, {
                        'line_id': line.id,
                        'nomenclature_id': line.nomenclature_id.id,
                        'qty': line.qty,
                        'serial_numbers': line.serial_numbers or '',
                    }))
            
            res['line_ids'] = wizard_lines
        
        return res
    
    def action_save_all_serials(self):
        """Зберігає всі серійні номери"""
        for line in self.line_ids:
            if line.serial_numbers:
                wizard = self.env['stock.serial.wizard'].create({
                    'document_model': self.document_model,
                    'document_id': self.document_id,
                    'line_id': line.line_id,
                    'nomenclature_id': line.nomenclature_id.id,
                    'qty': line.qty,
                    'serial_numbers': line.serial_numbers,
                })
                wizard.action_save_serials()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Успіх'),
                'message': _('Всі серійні номери збережено!'),
                'type': 'success',
                'sticky': False,
            }
        }


class StockSerialBulkLine(models.TransientModel):
    """Позиція wizard для масового введення серійних номерів"""
    _name = 'stock.serial.bulk.line'
    _description = 'Позиція для масового введення серійних номерів'

    wizard_id = fields.Many2one('stock.serial.bulk.wizard', 'Wizard', required=True, ondelete='cascade')
    line_id = fields.Integer('ID позиції документу', required=True)
    nomenclature_id = fields.Many2one('product.nomenclature', 'Товар', required=True)
    qty = fields.Float('Кількість', required=True)
    serial_numbers = fields.Text('Серійні номери')
    
    serial_count = fields.Integer(
        'Кількість S/N',
        compute='_compute_serial_count'
    )
    
    @api.depends('serial_numbers')
    def _compute_serial_count(self):
        """Підраховує кількість серійних номерів"""
        for line in self:
            if line.serial_numbers:
                serials = self.env['stock.serial.number']._parse_serial_text(line.serial_numbers)
                line.serial_count = len(serials)
            else:
                line.serial_count = 0
