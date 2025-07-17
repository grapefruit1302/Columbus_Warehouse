import logging
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, time, timedelta
import base64
import xlrd
import io

_logger = logging.getLogger(__name__)


class StockReceiptIncoming(models.Model):
    _name = 'stock.receipt.incoming'
    _description = 'Прихідна накладна'
    _inherit = ['stock.receipt.base']

    # Специфічні поля для прихідної накладної
    supplier_invoice_number = fields.Char('Номер розхідної постачальника', 
                                         help='Номер документа від постачальника',
                                         states={'posted': [('readonly', True)], 'confirmed': [('readonly', True)]})
    partner_id = fields.Many2one('res.partner', 'Постачальник', required=True,
                                domain="[('is_supplier', '=', True)]",
                                states={'posted': [('readonly', True)], 'confirmed': [('readonly', True)]})
    no_vat = fields.Boolean('Товар без ПДВ', default=False,
                            help='Якщо увімкнено, товари в цій накладній не обкладаються ПДВ',
                            states={'posted': [('readonly', True)], 'confirmed': [('readonly', True)]})
    line_ids = fields.One2many('stock.receipt.incoming.line', 'receipt_id', 'Позиції')

    # Реалізація абстрактних методів
    @api.model
    def _get_sequence_code(self):
        return 'stock.receipt.incoming'
    
    @api.model
    def _get_document_prefix(self):
        return 'ПН'
    
    @api.model
    def _get_posting_wizard_model(self):
        return 'stock.receipt.posting.wizard'
    
    @api.model
    def _get_report_template(self):
        return 'custom_stock_receipt.report_stock_receipt_incoming_template'
    
    def _get_lines_field(self):
        return 'line_ids'

    @api.depends('line_ids.nomenclature_id.tracking_serial')
    def _compute_has_serial_products(self):
        """Перевіряє чи є в документі товари з обліком по серійних номерах"""
        for record in self:
            record.has_serial_products = any(line.nomenclature_id.tracking_serial for line in record.line_ids)

    def action_print_receipt(self):
        """Друк прихідної накладної"""
        return self.action_print_document()

class StockReceiptIncomingLine(models.Model):
    _name = 'stock.receipt.incoming.line'
    _description = 'Позиція прихідної накладної'
    _inherit = ['stock.receipt.line.base']

    receipt_id = fields.Many2one('stock.receipt.incoming', 'Накладна', required=True, ondelete='cascade')
    
    # Специфічні поля для прихідної накладної
    vat_rate = fields.Float('Ставка ПДВ (%)', default=20.0)
    vat_amount = fields.Float('Сума ПДВ', compute='_compute_amounts', store=True, digits='Product Price')
    
    price_unit_with_vat = fields.Float('Ціна з ПДВ', default=0.0, digits='Product Price')
    amount_with_vat = fields.Float('Сума з ПДВ', compute='_compute_amounts', store=True, digits='Product Price')
    amount_no_vat = fields.Float('Сума без ПДВ', compute='_compute_amounts', store=True, digits='Product Price')
    
    no_vat = fields.Boolean('Без ПДВ', related='receipt_id.no_vat', readonly=True)

    # Реалізація абстрактних методів
    def _get_serial_wizard_model(self):
        return 'stock.receipt.serial.wizard'

    def _get_document_id(self):
        return self.receipt_id.id

    def _get_document_field_name(self):
        return 'receipt_id'

    @api.depends('qty', 'price_unit_no_vat', 'price_unit_with_vat', 'vat_rate', 'no_vat')
    def _compute_amounts(self):
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

    @api.onchange('price_unit_with_vat')
    def _onchange_price_with_vat(self):
        if self.price_unit_with_vat and not self.no_vat:
            self.price_unit_no_vat = 0.0

    @api.onchange('price_unit_no_vat')
    def _onchange_price_no_vat(self):
        if self.price_unit_no_vat and not self.no_vat:
            self.price_unit_with_vat = 0.0

class ProductNomenclatureWizard(models.Model):
    """Розширюємо модель product.nomenclature для wizard функціональності"""
    _inherit = 'product.nomenclature'

    def action_select_for_receipt(self):
        """Метод для вибору номенклатури в прихідній накладній"""
        line_id = self.env.context.get('line_id')
        receipt_id = self.env.context.get('receipt_id')
        
        if line_id:
            line = self.env['stock.receipt.incoming.line'].browse(line_id)
            line.nomenclature_id = self.id
        elif receipt_id:
            receipt = self.env['stock.receipt.incoming'].browse(receipt_id)
            self.env['stock.receipt.incoming.line'].create({
                'receipt_id': receipt_id,
                'nomenclature_id': self.id,
                'qty': 1.0,
            })
        
        return {'type': 'ir.actions.act_window_close'}


class StockReceiptPostingWizard(models.TransientModel):
    """Wizard для вибору часу проведення документа"""
    _name = 'stock.receipt.posting.wizard'
    _description = 'Проведення прихідної накладної'

    receipt_id = fields.Many2one('stock.receipt.incoming', 'Документ', required=True)
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
        
        # Встановлюємо receipt_id з контексту
        if self.env.context.get('active_id'):
            res['receipt_id'] = self.env.context['active_id']
        elif self.env.context.get('active_ids'):
            res['receipt_id'] = self.env.context['active_ids'][0]
        
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
        
        document = self.receipt_id
        
        custom_datetime = None
        if self.posting_time == 'custom_time':
            doc_date = document.date
            custom_datetime = datetime.combine(
                doc_date, 
                time(self.custom_hour, self.custom_minute, 0)
            )
        
        document._do_posting(self.posting_time, custom_datetime)
        return {'type': 'ir.actions.act_window_close'}