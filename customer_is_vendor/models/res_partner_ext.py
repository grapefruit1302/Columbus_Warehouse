# -*- coding: utf-8 -*-
from odoo import fields, models, api, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # is_customer = fields.Boolean(string='Is A Customer', defualt=False, tracking=True)
    is_vendor = fields.Boolean(string='Is A Vendor')
    is_customer = fields.Boolean(string='Is A Customer')

    @api.model
    def default_get(self, fields):
        res = super(ResPartner, self).default_get(fields)
        if self.customer_rank > 0:
            self.update({
                'is_customer': True
            })
        if self.supplier_rank > 0:
            self.update({
                'is_vendor': True
            })
        return res

    @api.onchange('is_vendor')
    def change_vendor_rank(self):
        vend = self.env['res.partner'].search([('id', '=', self.id.origin)])
        if not self.is_vendor:
            vend.supplier_rank = 0
        else:
            vend.supplier_rank = 1

    @api.onchange('is_customer')
    def chang_cust_rank(self):
        vend = self.env['res.partner'].search([('id', '=', self.id.origin)])
        if not self.is_customer:
            vend.customer_rank = 0
        else:
            vend.customer_rank = 1


