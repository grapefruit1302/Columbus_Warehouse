# custom_nomenclature/models/product_label_wizard.py
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class ProductLabelWizard(models.TransientModel):
    _name = 'product.label.wizard'
    _description = 'Product Label Wizard'

    product_id = fields.Many2one('product.nomenclature', string='Продукт', required=True)
    label_size = fields.Selection(
        selection=[
            ('58x40', '58x40 mm'),
            ('30x20', '30x20 mm'),
            ('40x25', '40x25 mm'),
        ],
        string='Розмір етикетки',
        default='58x40',
        required=True,
    )
    copy_count = fields.Integer('Кількість копій', default=1, required=True)
    barcode = fields.Char('Штрих-код', related='product_id.barcode')
    product_name = fields.Char('Назва', related='product_id.name')
    label_preview = fields.Html('Попередній перегляд', compute='_compute_label_preview')

    @api.depends('product_id', 'label_size', 'barcode', 'product_name')
    def _compute_label_preview(self):
        """Генерує HTML для попереднього перегляду етикетки."""
        for record in self:
            if record.product_id and record.barcode:
                # Рендеримо QWeb-шаблон у HTML
                template = self.env.ref('custom_nomenclature.product_label_template')
                html = template._render({
                    'doc': record,
                    'barcode_url': f"/report/barcode/?type=EAN13&value={record.barcode}&width=600&height=100",
                }, engine='qweb')
                record.label_preview = html
            else:
                record.label_preview = '<p>Штрих-код або продукт не вказані.</p>'

    def action_print(self):
        """Викликає звіт для друку етикетки з обраними параметрами."""
        if self.copy_count <= 0:
            raise ValidationError(_('Кількість копій має бути більше 0!'))
        return self.env.ref('custom_nomenclature.action_report_product_label_wizard').report_action(self)