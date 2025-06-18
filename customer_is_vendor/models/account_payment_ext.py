from odoo import api, models, fields


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    @api.onchange('partner_type')
    def _onchange_partner_type(self):
        domain = []
        if self.partner_type == 'customer':
            domain = [('customer_rank', '>', 0)]
        elif self.partner_type == 'supplier':
            domain = [('supplier_rank', '>', 0)]
        return {
            'domain': {'partner_id': domain}
        }
