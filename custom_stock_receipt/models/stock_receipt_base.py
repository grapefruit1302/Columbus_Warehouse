from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, time
from .utils import get_amount_in_words
import logging

_logger = logging.getLogger(__name__)


class StockReceiptBase(models.AbstractModel):
    """Базовий клас для всіх документів складського обліку"""
    _name = 'stock.receipt.base'
    _description = 'Базовий клас для документів складського обліку'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _rec_name = 'number'

    # Основні поля
    number = fields.Char('Номер', required=True, copy=False, readonly=True, 
                        index=True, default=lambda self: self._get_default_number())
    date = fields.Date('Дата', required=True, default=fields.Date.today, 
                       states={'posted': [('readonly', True)], 'confirmed': [('readonly', True)]})
    warehouse_id = fields.Many2one('stock.warehouse', 'Склад', required=True, 
                                   default=lambda self: self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1),
                                   states={'posted': [('readonly', True)], 'confirmed': [('readonly', True)]})
    company_id = fields.Many2one('res.company', 'Компанія', required=True,
                                 domain=lambda self: self._get_child_companies_domain(),
                                 states={'posted': [('readonly', True)], 'confirmed': [('readonly', True)]})
    
    # Статус документа
    state = fields.Selection([
        ('draft', 'Чернетка'),
        ('posted', 'Проведено'),
        ('confirmed', 'Підтверджено'),
        ('cancel', 'Скасовано')
    ], 'Статус', default='draft', tracking=True)
    
    # Поля для проведення
    posting_time = fields.Selection([
        ('start_of_day', 'Початок дня'),
        ('end_of_day', 'Кінець дня'),
        ('current_time', 'Поточний час'),
        ('custom_time', 'Власний час')
    ], 'Час проведення', readonly=True)
    posting_datetime = fields.Datetime('Дата та час проведення', readonly=True)
    
    # Додаткові поля
    notes = fields.Text('Примітки')
    has_serial_products = fields.Boolean('Має товари з серійними номерами', 
                                       compute='_compute_has_serial_products', store=True)

    # Абстрактні методи (повинні бути перевизначені в дочірніх класах)
    @api.model
    def _get_sequence_code(self):
        """Повертає код послідовності для нумерації документів"""
        raise NotImplementedError("Метод _get_sequence_code має бути перевизначений в дочірньому класі")
    
    @api.model
    def _get_document_prefix(self):
        """Повертає префікс документа (наприклад, 'ПН' для прихідної накладної)"""
        raise NotImplementedError("Метод _get_document_prefix має бути перевизначений в дочірньому класі")
    
    @api.model
    def _get_posting_wizard_model(self):
        """Повертає модель wizard для проведення"""
        raise NotImplementedError("Метод _get_posting_wizard_model має бути перевизначений в дочірньому класі")
    
    @api.model
    def _get_report_template(self):
        """Повертає шаблон для друку"""
        raise NotImplementedError("Метод _get_report_template має бути перевизначений в дочірньому класі")
    
    def _get_lines_field(self):
        """Повертає назву поля з позиціями документа"""
        raise NotImplementedError("Метод _get_lines_field має бути перевизначений в дочірньому класі")

    @api.depends()
    def _compute_has_serial_products(self):
        """Перевіряє чи є в документі товари з обліком по серійних номерах"""
        for record in self:
            line_ids = getattr(record, record._get_lines_field())
            record.has_serial_products = any(
                line.nomenclature_id.tracking_serial if hasattr(line, 'nomenclature_id') else False
                for line in line_ids
            )

    @api.model
    def _get_default_number(self):
        """Отримуємо наступний номер із послідовності"""
        company = self.env.company
        if company and company.name:
            words = company.name.split()
            company_prefix = words[1].upper()[:3] if len(words) >= 2 else words[0].upper()[:3] if words else 'XXX'
        else:
            company_prefix = 'XXX'
        
        sequence_code = self._get_sequence_code()
        context = {'ir_sequence_date': fields.Date.today()}
        next_seq = self.env['ir.sequence'].with_context(**context).with_company(company).next_by_code(sequence_code)
        
        if next_seq:
            import re
            numbers = re.findall(r'\d+', next_seq)
            seq_number = numbers[-1].zfill(8) if numbers else '00000001'
            return f"{company_prefix}-{self._get_document_prefix()}-{seq_number}"
        
        return f"{company_prefix}-{self._get_document_prefix()}-00000001"

    @api.model
    def create(self, vals):
        """Генерує номер документа при створенні"""
        company = self.env.company
        if company and company.name:
            words = company.name.split()
            company_prefix = words[1].upper()[:3] if len(words) >= 2 else words[0].upper()[:3] if words else 'XXX'
        else:
            company_prefix = 'XXX'
        
        doc_prefix = self._get_document_prefix()
        if (vals.get('number', 'Новий') in ['/', 'Новий'] or 
            not vals.get('number') or 
            vals.get('number').startswith(f"{company_prefix}-{doc_prefix}-")):
            vals['number'] = self._get_default_number()
            
        return super().create(vals)

    def get_amount_in_words(self, amount):
        """Перетворює суму в слова українською мовою"""
        return get_amount_in_words(amount)

    def action_post(self):
        """Відкриває wizard для вибору часу проведення"""
        lines_field = self._get_lines_field()
        if not getattr(self, lines_field):
            raise UserError('Додайте хоча б одну позицію до документа!')
        
        doc_date = self.date
        today = fields.Date.today()
        
        if doc_date == today:
            posting_options = [
                ('start_of_day', 'Початок дня'),
                ('end_of_day', 'Кінець дня'),
                ('current_time', 'Поточний час'),
                ('custom_time', 'Власний час')
            ]
        else:
            posting_options = [
                ('start_of_day', 'Початок вибраного дня'),
                ('end_of_day', 'Кінець вибраного дня')
            ]
        
        return {
            'name': 'Проведення документа',
            'type': 'ir.actions.act_window',
            'res_model': self._get_posting_wizard_model(),
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'posting_options': posting_options,
                'document_date': doc_date,
            }
        }

    def _do_posting(self, posting_time, custom_datetime=None):
        """Виконує проведення документа з вказаним часом"""
        self.ensure_one()
        
        doc_date = self.date
        
        if posting_time == 'start_of_day':
            posting_datetime = datetime.combine(doc_date, time(7, 0, 0))
        elif posting_time == 'end_of_day':
            posting_datetime = datetime.combine(doc_date, time(23, 0, 0))
        elif posting_time == 'custom_time' and custom_datetime:
            posting_datetime = custom_datetime
        else:
            posting_datetime = fields.Datetime.now()
        
        self.write({
            'state': 'posted',
            'posting_time': posting_time,
            'posting_datetime': posting_datetime,
        })
        
        self.message_post(
            body=f"Документ проведено: {self._get_posting_time_label(posting_time)} - {posting_datetime}."
        )
        
        return True

    def _get_posting_time_label(self, posting_time):
        """Повертає текстову мітку для часу проведення"""
        labels = {
            'start_of_day': 'На початок дня',
            'end_of_day': 'На кінець дня',
            'current_time': 'Поточний час',
            'custom_time': 'Власний час'
        }
        return labels.get(posting_time, posting_time)

    def action_confirm(self):
        """Підтверджує документ"""
        self.ensure_one()
        if self.state != 'posted':
            raise UserError('Спочатку проведіть документ!')
        
        self.state = 'confirmed'

    def action_cancel(self):
        """Скасовує документ"""
        self.ensure_one()
        self.state = 'cancel'

    def action_reset_to_draft(self):
        """Повертає в чернетку"""
        self.ensure_one()
        self.write({
            'state': 'draft',
            'posting_time': False,
            'posting_datetime': False,
        })

    def action_print_document(self):
        """Друк документа"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.report',
            'report_name': self._get_report_template(),
            'report_type': 'qweb-pdf',
            'name': f'{self._get_document_prefix()} {self.number}',
            'context': dict(self.env.context, active_ids=self.ids),
            'data': {
                'report_name': f'{self.number}'
            }
        }

    def _get_child_companies_domain(self):
        """Отримує домен для дочірніх компаній (гілок)"""
        allowed_company_ids = self.env.context.get('allowed_company_ids', [])
        if allowed_company_ids:
            companies = self.env['res.company'].browse(allowed_company_ids)
        else:
            companies = self.env.company
        
        child_company_ids = set()
        for company in companies:
            child_company_ids.update(company.child_ids.ids)
        
        _logger.info(f"Allowed company IDs: {allowed_company_ids}")
        _logger.info(f"Found child company IDs: {child_company_ids}")
        
        if child_company_ids:
            return [('id', 'in', list(child_company_ids))]
        else:
            _logger.warning("No child companies found")
            return [('id', '=', False)]

    @api.onchange('company_id')
    def _onchange_company_id(self):
        """Перевірка, чи вибрана компанія є дочірньою"""
        if self.company_id and not self.company_id.parent_id:
            _logger.warning(f"Selected company {self.company_id.name} is not a child company")
            self.company_id = False
            return {
                'warning': {
                    'title': 'Помилка',
                    'message': 'Будь ласка, оберіть дочірню компанію (гілку), а не головну компанію.'
                }
            }


class StockReceiptLineBase(models.AbstractModel):
    """Базовий клас для позицій документів складського обліку"""
    _name = 'stock.receipt.line.base'
    _description = 'Базовий клас для позицій документів складського обліку'

    # Спільні поля для всіх позицій
    nomenclature_id = fields.Many2one('product.nomenclature', 'Номенклатура', required=True)
    product_name = fields.Char('Назва товару', related='nomenclature_id.name', readonly=True)
    product_code = fields.Char('Код товару', related='nomenclature_id.code', readonly=True)
    product_barcode = fields.Char('Штрих-код', related='nomenclature_id.barcode', readonly=True)
    
    product_uom_id = fields.Many2one('uom.uom', 'Од. виміру', related='nomenclature_id.base_uom_id', readonly=True)
    selected_uom_id = fields.Many2one('uom.uom', 'Обрана од. виміру', 
                                     domain="[('id', 'in', available_uom_ids)]")
    available_uom_ids = fields.Many2many('uom.uom', compute='_compute_available_uoms')
    
    qty = fields.Float('Кількість', default=1.0, required=True)
    price_unit_no_vat = fields.Float('Ціна без ПДВ', default=0.0, digits='Product Price')
    
    location_id = fields.Many2one('stock.location', 'Локація')
    lot_ids = fields.Many2many('stock.lot', string='Серійні номери/Лоти')
    notes = fields.Char('Примітки')
    
    # Поля для серійних номерів
    tracking_serial = fields.Boolean('Облік по S/N', related='nomenclature_id.tracking_serial', readonly=True)
    serial_numbers = fields.Text('Серійні номери', help='Введіть серійні номери, розділені комою або новим рядком')
    serial_count = fields.Integer('Кількість S/N', compute='_compute_serial_count', store=True)

    @api.depends('serial_numbers')
    def _compute_serial_count(self):
        for line in self:
            if line.serial_numbers:
                serials = [s.strip() for s in line.serial_numbers.replace('\n', ',').split(',') if s.strip()]
                line.serial_count = len(serials)
            else:
                line.serial_count = 0

    @api.depends('nomenclature_id')
    def _compute_available_uoms(self):
        for line in self:
            if line.nomenclature_id and line.nomenclature_id.uom_line_ids:
                line.available_uom_ids = line.nomenclature_id.uom_line_ids.mapped('uom_id')
            else:
                line.available_uom_ids = False

    @api.onchange('nomenclature_id')
    def _onchange_nomenclature_id(self):
        if self.nomenclature_id:
            default_uom_line = self.nomenclature_id.uom_line_ids.filtered('is_default')
            if default_uom_line:
                self.selected_uom_id = default_uom_line[0].uom_id
            else:
                self.selected_uom_id = self.nomenclature_id.base_uom_id

    def action_input_serial_numbers(self):
        """Відкриває wizard для введення серійних номерів"""
        self.ensure_one()
        
        if not self.tracking_serial:
            raise UserError('Обраний товар не має обліку по серійних номерах!')
        
        return {
            'name': 'Введення серійних номерів',
            'type': 'ir.actions.act_window',
            'res_model': self._get_serial_wizard_model(),
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_selected_line_id': self.id,
                'default_document_id': self._get_document_id(),
            }
        }

    def _get_serial_wizard_model(self):
        """Повертає модель wizard для серійних номерів"""
        raise NotImplementedError("Метод _get_serial_wizard_model має бути перевизначений в дочірньому класі")

    def _get_document_id(self):
        """Повертає ID документа"""
        raise NotImplementedError("Метод _get_document_id має бути перевизначений в дочірньому класі")

    def _get_document_field_name(self):
        """Повертає назву поля документа"""
        raise NotImplementedError("Метод _get_document_field_name має бути перевизначений в дочірньому класі")

    @api.constrains('nomenclature_id')
    def _check_unique_nomenclature(self):
        """Перевіряє унікальність номенклатури в межах одного документа"""
        for line in self:
            if line.nomenclature_id:
                document_field = line._get_document_field_name()
                document_id = getattr(line, document_field).id
                
                duplicate_lines = self.search([
                    (document_field, '=', document_id),
                    ('nomenclature_id', '=', line.nomenclature_id.id),
                    ('id', '!=', line.id)
                ])
                if duplicate_lines:
                    raise ValidationError(
                        f'Товар "{line.nomenclature_id.name}" вже додано до цього документа! '
                        f'Для зміни кількості відредагуйте існуючу позицію.'
                    )

    @api.model
    def create(self, vals):
        """Перевірка при створенні нової позиції"""
        line = super().create(vals)
        line._check_unique_nomenclature()
        return line

    def write(self, vals):
        """Перевірка при зміні позиції"""
        result = super().write(vals)
        if 'nomenclature_id' in vals:
            self._check_unique_nomenclature()
        return result