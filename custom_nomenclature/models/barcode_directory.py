from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class BarcodeDirectory(models.Model):
    _name = 'barcode.directory'
    _description = 'Barcode Directory'
    _order = 'barcode'

    barcode = fields.Char('Штрих-код', required=True, index=True)
    product_id = fields.Many2one('product.nomenclature', 'Продукт', index=True)
    active = fields.Boolean('Активний', default=True)
    created_date = fields.Datetime('Дата створення', default=fields.Datetime.now, readonly=True)

    _sql_constraints = [
        ('barcode_uniq', 'unique(barcode)', 'Штрих-код має бути унікальним!')
    ]

    @api.constrains('barcode')
    def _check_barcode_format(self):
        """Перевіряє, що штрих-код відповідає формату EAN13."""
        for record in self:
            if not record._is_valid_ean13(record.barcode):
                raise ValidationError(_('Штрих-код EAN13 має містити 13 цифр і бути валідним!'))

    def _is_valid_ean13(self, barcode):
        """Перевіряє валідність EAN13."""
        if not barcode or not barcode.isdigit() or len(barcode) != 13:
            return False
        try:
            total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(barcode[:-1]))
            check_digit = (10 - (total % 10)) % 10
            return int(barcode[-1]) == check_digit
        except Exception as e:
            _logger.error("Помилка перевірки EAN13: %s", e)
            return False