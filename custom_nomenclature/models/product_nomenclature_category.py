from odoo import api, fields, models

class ProductNomenclatureCategory(models.Model):
    _name = 'product.nomenclature.category'
    _description = 'Product Nomenclature Category'
    _parent_name = "parent_id"
    _parent_store = True
    _rec_name = 'complete_name'
    _order = 'complete_name'

    name = fields.Char('Назва', required=True, translate=True)
    complete_name = fields.Char('Complete Name', compute='_compute_complete_name', store=True)
    parent_id = fields.Many2one('product.nomenclature.category', 'Parent Category', index=True, ondelete='cascade')
    parent_path = fields.Char(index=True)
    child_id = fields.One2many('product.nomenclature.category', 'parent_id', 'Child Categories')
    product_nomenclature_ids = fields.One2many('product.nomenclature', 'category_id', string='Products')
    product_count = fields.Integer(
        'Product Count', compute='_compute_product_count',
        help="The number of products under this category")

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for category in self:
            if category.parent_id:
                category.complete_name = '%s / %s' % (category.parent_id.complete_name, category.name)
            else:
                category.complete_name = category.name

    def _compute_product_count(self):
        for category in self:
            category.product_count = self.env['product.nomenclature'].search_count([
                ('category_id', 'child_of', category.id)
            ])
    
    def action_open_products(self):
        return {
            'name': 'Products',
            'type': 'ir.actions.act_window',
            'res_model': 'product.nomenclature',
            'view_mode': 'list,form',
            'domain': [('category_id', 'child_of', self.id)],
            'context': {'default_category_id': self.id},
        }