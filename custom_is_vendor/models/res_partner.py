from odoo import api, fields, models

class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_supplier = fields.Boolean(
        string='Є постачальником',
        default=False,
        help='Відмітьте, якщо цей контакт є постачальником'
    )

    contact_type = fields.Selection(
        selection='_get_contact_type_selection',
        string='Тип контакту',
        default='other',
        required=True
    )

    @api.model
    def _get_contact_type_selection(self):
        categories = self.env['contact.category'].search([], order='sequence, name')
        return [(cat.code, cat.name) for cat in categories] + [('other', 'Інше')]

    def name_get(self):
        result = []
        for record in self:
            name = record.name or ''
            if record.contact_type and record.contact_type != 'other':
                categories = self.env['contact.category'].search([('code', '=', record.contact_type)])
                prefix = f'[{categories[0].name[0]}]' if categories else ''
                name = f"{prefix} {name}".strip()
            result.append((record.id, name))
        return result