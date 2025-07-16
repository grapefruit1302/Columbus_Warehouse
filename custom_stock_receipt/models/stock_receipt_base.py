from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class StockReceiptBase(models.AbstractModel):
    """Базовий клас для всіх документів надходження"""
    _name = 'stock.receipt.base'
    _description = 'Базовий клас документів надходження'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, number desc'

    number = fields.Char(
        'Номер документа',
        required=True,
        copy=False,
        readonly=True,
        default='Новий',
        tracking=True,
        help='Унікальний номер документа'
    )
    
    date = fields.Date(
        'Дата документа',
        required=True,
        default=fields.Date.today,
        tracking=True,
        help='Дата створення документа'
    )
    
    company_id = fields.Many2one(
        'res.company',
        'Компанія',
        required=True,
        default=lambda self: self.env.company,
        tracking=True
    )
    
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        'Склад',
        required=True,
        tracking=True,
        help='Склад куди надходять товари'
    )
    
    state = fields.Selection([
        ('draft', 'Чернетка'),
        ('confirmed', 'Підтверджено'),
        ('posted', 'Проведено'),
        ('cancelled', 'Скасовано')
    ], 'Статус', default='draft', tracking=True, required=True)
    
    posting_datetime = fields.Datetime(
        'Час проведення',
        readonly=True,
        tracking=True,
        help='Коли документ був проведений'
    )
    
    posting_time = fields.Selection([
        ('start_of_day', 'Початок дня'),
        ('end_of_day', 'Кінець дня'),
        ('current_time', 'Поточний час'),
        ('custom_time', 'Власний час')
    ], 'Час проведення', default='current_time')
    
    notes = fields.Text(
        'Примітки',
        help='Додаткові примітки до документа'
    )
    
    has_serial_products = fields.Boolean(
        'Є товари з S/N',
        compute='_compute_has_serial_products',
        help='Чи є в документі товари з обліком по серійних номерах'
    )
    
    total_amount_no_vat = fields.Float(
        'Сума без ПДВ',
        compute='_compute_totals',
        store=True,
        digits='Product Price',
        help='Загальна сума без ПДВ'
    )
    
    total_vat_amount = fields.Float(
        'Сума ПДВ',
        compute='_compute_totals',
        store=True,
        digits='Product Price',
        help='Загальна сума ПДВ'
    )
    
    total_amount_with_vat = fields.Float(
        'Сума з ПДВ',
        compute='_compute_totals',
        store=True,
        digits='Product Price',
        help='Загальна сума з ПДВ'
    )
    
    line_count = fields.Integer(
        'Кількість позицій',
        compute='_compute_line_count',
        help='Кількість позицій в документі'
    )
    
    line_ids = fields.One2many(
        'stock.receipt.base.line',  # Буде перевизначено в дочірніх класах
        'receipt_id',
        'Позиції документа'
    )
    
    @api.model
    def create(self, vals):
        """Генерує номер документа при створенні"""
        if vals.get('number', 'Новий') == 'Новий':
            vals['number'] = self._generate_number()
        return super().create(vals)
    
    def _generate_number(self):
        """Абстрактний метод для генерації номера документа
        
        Має бути перевизначений в дочірніх класах
        """
        raise NotImplementedError("Subclasses must implement _generate_number")
    
    @api.depends('line_ids.nomenclature_id.tracking_serial')
    def _compute_has_serial_products(self):
        """Перевіряє чи є товари з обліком по серійних номерах"""
        for record in self:
            record.has_serial_products = any(
                line.nomenclature_id.tracking_serial for line in record.line_ids
            )
    
    @api.depends('line_ids.amount_no_vat', 'line_ids.vat_amount', 'line_ids.amount_with_vat')
    def _compute_totals(self):
        """Обчислює загальні суми"""
        for record in self:
            record.total_amount_no_vat = sum(line.amount_no_vat for line in record.line_ids)
            record.total_vat_amount = sum(line.vat_amount for line in record.line_ids)
            record.total_amount_with_vat = sum(line.amount_with_vat for line in record.line_ids)
    
    @api.depends('line_ids')
    def _compute_line_count(self):
        """Обчислює кількість позицій"""
        for record in self:
            record.line_count = len(record.line_ids)
    
    def action_confirm(self):
        """Підтверджує документ"""
        self._validate_before_confirm()
        self.state = 'confirmed'
        self.message_post(body=_('Документ підтверджено'))
    
    def action_cancel(self):
        """Скасовує документ"""
        if self.state == 'posted':
            raise UserError(_('Неможливо скасувати проведений документ!'))
        
        self.state = 'cancelled'
        self.message_post(body=_('Документ скасовано'))
    
    def action_reset_to_draft(self):
        """Повертає документ в чернетку"""
        if self.state == 'posted':
            raise UserError(_('Неможливо повернути проведений документ в чернетку!'))
        
        self.state = 'draft'
        self.posting_datetime = False
        self.message_post(body=_('Документ повернуто в чернетку'))
    
    def action_post(self):
        """Проводить документ"""
        self._validate_before_posting()
        
        if self.posting_time == 'custom_time':
            return self._show_posting_wizard()
        
        self._do_posting()
        return True
    
    def _do_posting(self, custom_datetime=None):
        """Виконує проведення документа"""
        posting_datetime = self._calculate_posting_datetime(custom_datetime)
        
        self._process_document_posting(posting_datetime)
        
        self.write({
            'state': 'posted',
            'posting_datetime': posting_datetime
        })
        
        self.message_post(body=_('Документ проведено о %s') % posting_datetime.strftime('%Y-%m-%d %H:%M:%S'))
    
    def _calculate_posting_datetime(self, custom_datetime=None):
        """Розраховує час проведення"""
        if custom_datetime:
            return custom_datetime
        
        from datetime import datetime, time
        
        doc_date = self.date
        
        if self.posting_time == 'start_of_day':
            return datetime.combine(doc_date, time(0, 0, 0))
        elif self.posting_time == 'end_of_day':
            return datetime.combine(doc_date, time(23, 59, 59))
        else:  # current_time
            return fields.Datetime.now()
    
    def _show_posting_wizard(self):
        """Показує wizard для вибору часу проведення"""
        return {
            'name': _('Час проведення документа'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.receipt.posting.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_receipt_id': self.id,
                'default_posting_time': self.posting_time,
            }
        }
    
    def _process_document_posting(self, posting_datetime):
        """Абстрактний метод для обробки проведення документа
        
        Має бути перевизначений в дочірніх класах для реалізації
        специфічної логіки проведення (створення партій, оновлення залишків тощо)
        """
        raise NotImplementedError("Subclasses must implement _process_document_posting")
    
    def _validate_before_confirm(self):
        """Валідація перед підтвердженням"""
        self._validate_lines_exist()
        self._validate_required_fields()
    
    def _validate_before_posting(self):
        """Валідація перед проведенням"""
        if self.state != 'confirmed':
            raise UserError(_('Документ має бути підтверджений перед проведенням!'))
        
        self._validate_lines_exist()
        self._validate_serial_numbers()
        self._validate_quantities()
    
    def _validate_lines_exist(self):
        """Перевіряє наявність позицій"""
        if not self.line_ids:
            raise UserError(_('Додайте хоча б одну позицію до документа!'))
    
    def _validate_required_fields(self):
        """Перевіряє обов'язкові поля"""
        if not self.warehouse_id:
            raise UserError(_('Вкажіть склад!'))
        
        if not self.company_id:
            raise UserError(_('Вкажіть компанію!'))
    
    def _validate_serial_numbers(self):
        """Валідація серійних номерів"""
        for line in self.line_ids.filtered('nomenclature_id.tracking_serial'):
            if not line.serial_numbers:
                raise UserError(
                    _('Введіть серійні номери для товару: %s') % line.nomenclature_id.name
                )
            
            serials = self.env['stock.serial.number']._parse_serial_text(line.serial_numbers)
            if len(serials) != int(line.qty):
                raise UserError(
                    _('Кількість серійних номерів (%d) не відповідає кількості товару (%d) для: %s') % 
                    (len(serials), line.qty, line.nomenclature_id.name)
                )
    
    def _validate_quantities(self):
        """Перевіряє коректність кількостей"""
        for line in self.line_ids:
            if line.qty <= 0:
                raise UserError(
                    _('Кількість має бути більше нуля для товару: %s') % line.nomenclature_id.name
                )
    
    def action_view_lines(self):
        """Показує позиції документа"""
        return {
            'name': _('Позиції документа'),
            'type': 'ir.actions.act_window',
            'res_model': self.line_ids._name,
            'view_mode': 'list,form',
            'domain': [('receipt_id', '=', self.id)],
            'context': {'default_receipt_id': self.id},
        }
    
    def action_input_serial_numbers(self):
        """Універсальний метод для введення серійних номерів"""
        if not self.has_serial_products:
            raise UserError(_('У документі немає товарів з обліком по серійних номерах!'))
        
        return {
            'name': _('Введення серійних номерів'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.serial.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_model': self._name,
                'default_document_id': self.id,
            }
        }
    
    def get_amount_in_words(self):
        """Отримує суму прописом (делегує до сервісу)"""
        from ..services.currency_service import CurrencyService
        return CurrencyService.amount_to_words_ua(self.total_amount_with_vat or self.total_amount_no_vat)
    
    def _get_child_companies_domain(self):
        """Отримує домен для дочірніх компаній"""
        company_ids = [self.company_id.id]
        
        def add_children(parent_company):
            children = self.env['res.company'].search([('parent_id', '=', parent_company.id)])
            for child in children:
                if child.id not in company_ids:
                    company_ids.append(child.id)
                    add_children(child)
        
        add_children(self.company_id)
        return [('id', 'in', company_ids)]
    
    @api.onchange('company_id')
    def _onchange_company_id(self):
        """Очищає склад при зміні компанії"""
        if self.company_id:
            self.warehouse_id = False
    
    def copy(self, default=None):
        """Копіює документ з очищенням специфічних полів"""
        default = dict(default or {})
        default.update({
            'number': 'Новий',
            'state': 'draft',
            'posting_datetime': False,
        })
        return super().copy(default)


class StockReceiptBaseLine(models.AbstractModel):
    """Базовий клас для позицій документів надходження"""
    _name = 'stock.receipt.base.line'
    _description = 'Базова позиція документа надходження'
    _order = 'sequence, id'

    sequence = fields.Integer('Послідовність', default=10)
    
    receipt_id = fields.Many2one(
        'stock.receipt.base',  # Буде перевизначено в дочірніх класах
        'Документ',
        required=True,
        ondelete='cascade'
    )
    
    nomenclature_id = fields.Many2one(
        'product.nomenclature',
        'Товар',
        required=True
    )
    
    qty = fields.Float(
        'Кількість',
        required=True,
        default=1.0,
        digits='Product Unit of Measure'
    )
    
    selected_uom_id = fields.Many2one(
        'uom.uom',
        'Одиниця виміру',
        required=True
    )
    
    tracking_serial = fields.Boolean(
        'Облік по S/N',
        related='nomenclature_id.tracking_serial',
        readonly=True
    )
    
    serial_numbers = fields.Text(
        'Серійні номери',
        help='Введіть серійні номери, розділені комою або новим рядком'
    )
    
    serial_count = fields.Integer(
        'Кількість S/N',
        compute='_compute_serial_count',
        store=True
    )
    
    price_unit_no_vat = fields.Float(
        'Ціна без ПДВ',
        default=0.0,
        digits='Product Price'
    )
    
    vat_rate = fields.Float(
        'Ставка ПДВ (%)',
        default=20.0
    )
    
    amount_no_vat = fields.Float(
        'Сума без ПДВ',
        compute='_compute_amounts',
        store=True,
        digits='Product Price'
    )
    
    vat_amount = fields.Float(
        'Сума ПДВ',
        compute='_compute_amounts',
        store=True,
        digits='Product Price'
    )
    
    price_unit_with_vat = fields.Float(
        'Ціна з ПДВ',
        default=0.0,
        digits='Product Price'
    )
    
    amount_with_vat = fields.Float(
        'Сума з ПДВ',
        compute='_compute_amounts',
        store=True,
        digits='Product Price'
    )
    
    no_vat = fields.Boolean(
        'Без ПДВ',
        related='receipt_id.no_vat',
        readonly=True
    )
    
    notes = fields.Char('Примітки')
    
    @api.depends('serial_numbers')
    def _compute_serial_count(self):
        """Підраховує кількість серійних номерів"""
        for line in self:
            if line.serial_numbers:
                serials = self.env['stock.serial.number']._parse_serial_text(line.serial_numbers)
                line.serial_count = len(serials)
            else:
                line.serial_count = 0
    
    @api.depends('qty', 'price_unit_no_vat', 'price_unit_with_vat', 'vat_rate', 'no_vat')
    def _compute_amounts(self):
        """Обчислює суми"""
        for line in self:
            if line.no_vat:
                line.amount_no_vat = line.qty * line.price_unit_no_vat
                line.vat_amount = 0.0
                line.price_unit_with_vat = 0.0
                line.amount_with_vat = 0.0
            else:
                if line.price_unit_no_vat and not line.price_unit_with_vat:
                    line.price_unit_with_vat = line.price_unit_no_vat * (1 + line.vat_rate / 100)
                elif line.price_unit_with_vat and not line.price_unit_no_vat:
                    line.price_unit_no_vat = line.price_unit_with_vat / (1 + line.vat_rate / 100)
                
                line.amount_no_vat = line.qty * line.price_unit_no_vat
                line.vat_amount = line.amount_no_vat * (line.vat_rate / 100)
                line.amount_with_vat = line.amount_no_vat + line.vat_amount
    
    @api.onchange('nomenclature_id')
    def _onchange_nomenclature_id(self):
        """Встановлює одиницю виміру при виборі товару"""
        if self.nomenclature_id:
            if hasattr(self.nomenclature_id, 'base_uom_id'):
                self.selected_uom_id = self.nomenclature_id.base_uom_id
    
    def action_input_serial_numbers(self):
        """Відкриває wizard для введення серійних номерів"""
        self.ensure_one()
        
        if not self.tracking_serial:
            raise UserError(_('Обраний товар не має обліку по серійних номерах!'))
        
        return {
            'name': _('Введення серійних номерів'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.serial.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_model': self.receipt_id._name,
                'default_document_id': self.receipt_id.id,
                'default_line_id': self.id,
                'default_nomenclature_id': self.nomenclature_id.id,
                'default_qty': self.qty,
            }
        }
