from odoo import fields, models

class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_supplier = fields.Boolean(string='Is Supplier', default=False)