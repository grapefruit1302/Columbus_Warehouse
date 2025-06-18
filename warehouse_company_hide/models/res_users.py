from odoo import models, fields, api

class ResUsers(models.Model):
    _inherit = 'res.users'

    # Нове поле для вибору однієї компанії
    single_company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        help="The single company this user is allowed to access."
    )

    # Перевизначимо company_ids, щоб синхронізувати його з single_company_id
    @api.depends('single_company_id')
    def _compute_company_ids(self):
        for user in self:
            if user.single_company_id:
                user.company_ids = [(6, 0, [user.single_company_id.id])]
            else:
                user.company_ids = [(6, 0, [])]

    # Зворотна синхронізація (якщо змінюється company_ids)
    @api.onchange('company_ids')
    def _onchange_company_ids(self):
        if self.company_ids:
            self.single_company_id = self.company_ids[0]
        else:
            self.single_company_id = False

    # Обмеження: лише одна компанія
    @api.constrains('company_ids')
    def _check_single_company(self):
        for user in self:
            if len(user.company_ids) > 1:
                user.company_ids = [(6, 0, [user.single_company_id.id])]