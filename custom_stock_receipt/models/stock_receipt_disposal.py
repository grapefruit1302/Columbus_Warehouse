from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, time
import logging

from ..services.currency_service import CurrencyService
from ..services.numbering_service import NumberingService

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        context = self.env.context
        
        # Перевіряємо, чи виклик походить від stock.receipt.disposal
        if context.get('_get_child_companies_domain') == 'stock.receipt.disposal,_get_child_companies_domain':
            _logger.info("Custom name_search for stock.receipt.disposal triggered")
            # Отримуємо компанії з контексту
            allowed_company_ids = context.get('allowed_company_ids', [])
            child_company_ids = set()
            if allowed_company_ids:
                companies = self.browse(allowed_company_ids)
                for company in companies:
                    child_company_ids.update(company.child_ids.ids)
            else:
                child_company_ids.update(self.env.company.child_ids.ids)
            
            # Формуємо домен тільки для дочірніх компаній
            domain = [('id', 'in', list(child_company_ids))] if child_company_ids else [('id', '=', False)]
            if name:
                domain += ['|', ('name', operator, name), ('display_name', operator, name)]
            
            _logger.info(f"Custom name_search domain: {domain}")
            # Виконуємо пошук і повертаємо список кортежів (id, name)
            companies = self.search(domain + args, limit=limit)
            return [(company.id, company.display_name) for company in companies]
        
        # Перевіряємо, чи виклик походить від stock.receipt.incoming (існуюча логіка)
        elif context.get('_get_child_companies_domain') == 'stock.receipt.incoming,_get_child_companies_domain':
            _logger.info("Custom name_search for stock.receipt.incoming triggered")
            # Отримуємо компанії з контексту
            allowed_company_ids = context.get('allowed_company_ids', [])
            child_company_ids = set()
            if allowed_company_ids:
                companies = self.browse(allowed_company_ids)
                for company in companies:
                    child_company_ids.update(company.child_ids.ids)
            else:
                child_company_ids.update(self.env.company.child_ids.ids)
            
            # Формуємо домен тільки для дочірніх компаній
            domain = [('id', 'in', list(child_company_ids))] if child_company_ids else [('id', '=', False)]
            if name:
                domain += ['|', ('name', operator, name), ('display_name', operator, name)]
            
            _logger.info(f"Custom name_search domain: {domain}")
            # Виконуємо пошук і повертаємо список кортежів (id, name)
            companies = self.search(domain + args, limit=limit)
            return [(company.id, company.display_name) for company in companies]
        
        # Для інших випадків викликаємо стандартну логіку
        _logger.info("Falling back to super name_search")
        return super(ResCompany, self).name_search(name, args, operator, limit)


class StockReceiptDisposal(models.Model):
    _name = 'stock.receipt.disposal'
    _description = 'Акт оприходування'
    _order = 'date desc, id desc'
    _rec_name = 'number'
    _inherit = [
        'stock.receipt.base',
        'serial.tracking.mixin',
        'document.validation.mixin',
        'workflow.mixin'
    ]

    line_ids = fields.One2many('stock.receipt.disposal.line', 'disposal_id', 'Позиції')

    @api.model
    def create(self, vals):
        """Генеруємо номер документа при створенні"""
        if not vals.get('number') or vals.get('number') in ['/', 'Новий']:
            vals['number'] = NumberingService.generate_receipt_number('disposal', self.env)
        return super(StockReceiptDisposal, self).create(vals)

    def _get_amount_in_words(self, amount):
        """Перетворює суму в слова українською мовою"""
        return CurrencyService.amount_to_words_ua(amount)

    def action_post(self):
        """Відкриває wizard для вибору часу проведення"""
        if not self.line_ids:
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
            'res_model': 'stock.disposal.posting.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_disposal_id': self.id,
                'posting_options': posting_options,
                'document_date': doc_date,
            }
        }

    def _do_posting(self, posting_time, custom_datetime=None):
        """Виконує проведення документа з вказаним часом"""
        self.ensure_one()
        
        doc_date = self.date
        
        if posting_time == 'start_of_day':
            posting_datetime = datetime.combine(doc_date, time(0, 0, 0))
        elif posting_time == 'end_of_day':
            posting_datetime = datetime.combine(doc_date, time(23, 59, 59))
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

    def action_print_disposal(self):
        """Друк акту оприходування"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.report',
            'report_name': 'custom_stock_receipt.report_stock_receipt_disposal_template',
            'report_type': 'qweb-pdf',
            'name': f'Акт оприходування {self.number}',
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


class StockReceiptDisposalLine(models.Model):
    _name = 'stock.receipt.disposal.line'
    _description = 'Позиція акта оприходування'

    disposal_id = fields.Many2one('stock.receipt.disposal', 'Акт', required=True, ondelete='cascade')
    
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
    amount_no_vat = fields.Float('Сума без ПДВ', compute='_compute_amounts', store=True, digits='Product Price')
    
    location_id = fields.Many2one('stock.location', 'Локація')
    lot_ids = fields.Many2many('stock.lot', string='Серійні номери/Лоти')
    notes = fields.Char('Примітки')
    
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

    @api.depends('qty', 'price_unit_no_vat')
    def _compute_amounts(self):
        for line in self:
            line.amount_no_vat = line.qty * line.price_unit_no_vat

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
        self.ensure_one()
        
        if not self.tracking_serial:
            raise UserError('Обраний товар не має обліку по серійних номерах!')
        
        return {
            'name': 'Введення серійних номерів',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.disposal.serial.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_disposal_id': self.disposal_id.id,
                'default_selected_line_id': self.id,
            }
        }

    @api.constrains('nomenclature_id', 'disposal_id')
    def _check_unique_nomenclature(self):
        """Перевіряє унікальність номенклатури в межах одного документа"""
        for line in self:
            if line.nomenclature_id and line.disposal_id:
                # Шукаємо інші позиції з такою ж номенклатурою в цьому ж документі
                duplicate_lines = self.search([
                    ('disposal_id', '=', line.disposal_id.id),
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


class ProductNomenclatureWizard(models.Model):
    """Розширюємо модель product.nomenclature для wizard функціональності"""
    _inherit = 'product.nomenclature'

    def action_select_for_disposal(self):
        """Метод для вибору номенклатури в акті оприходування"""
        line_id = self.env.context.get('line_id')
        disposal_id = self.env.context.get('disposal_id')
        
        if line_id:
            line = self.env['stock.receipt.disposal.line'].browse(line_id)
            line.nomenclature_id = self.id
        elif disposal_id:
            disposal = self.env['stock.receipt.disposal'].browse(disposal_id)
            self.env['stock.receipt.disposal.line'].create({
                'disposal_id': disposal_id,
                'nomenclature_id': self.id,
                'qty': 1.0,
            })
        
        return {'type': 'ir.actions.act_window_close'}


class StockDisposalPostingWizard(models.TransientModel):
    """Wizard для вибору часу проведення документа"""
    _name = 'stock.disposal.posting.wizard'
    _description = 'Проведення акту оприходування'

    disposal_id = fields.Many2one('stock.receipt.disposal', 'Документ', required=True)
    posting_time = fields.Selection([
        ('start_of_day', 'Початок дня'),
        ('end_of_day', 'Кінець дня'),
        ('current_time', 'Поточний час'),
        ('custom_time', 'Власний час')
    ], 'Час проведення', required=True, default='current_time')
    
    custom_hour = fields.Integer('Година', default=12)
    custom_minute = fields.Integer('Хвилина', default=0)
    
    @api.model
    def default_get(self, fields_list):
        """Встановлює доступні опції залежно від дати документа"""
        res = super().default_get(fields_list)
        
        if self.env.context.get('posting_options'):
            posting_options = self.env.context.get('posting_options')
            if posting_options and posting_options[0]:
                res['posting_time'] = posting_options[0][0]
        
        return res
    
    @api.constrains('custom_hour', 'custom_minute')
    def _check_custom_time(self):
        """Перевірка коректності введеного часу"""
        for wizard in self:
            if wizard.posting_time == 'custom_time':
                if not (0 <= wizard.custom_hour <= 23):
                    raise ValidationError('Година має бути від 0 до 23!')
                if not (0 <= wizard.custom_minute <= 59):
                    raise ValidationError('Хвилина має бути від 0 до 59!')

    def action_confirm_posting(self):
        """Підтверджує проведення з вибраним часом"""
        self.ensure_one()
        
        custom_datetime = None
        if self.posting_time == 'custom_time':
            doc_date = self.disposal_id.date
            custom_datetime = datetime.combine(
                doc_date, 
                time(self.custom_hour, self.custom_minute, 0)
            )
        
        self.disposal_id._do_posting(self.posting_time, custom_datetime)
        return {'type': 'ir.actions.act_window_close'}
