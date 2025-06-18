from odoo import models, fields, api
from odoo.exceptions import ValidationError
import re

class StockRegion(models.Model):
    _name = 'stock.region'
    _description = 'Район складу'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    code = fields.Char(string='Код', size=2, required=True)
    name = fields.Char(string='Найменування', required=True)
    active = fields.Boolean(string='Активний', default=True)
    company_id = fields.Many2one(
        'res.company', 
        string='Компанія',
        required=True,
        default=lambda self: self._get_default_company(),
        domain=[('parent_id', '=', False)]
    )

    @api.model
    def _get_default_company(self):
        """Повертає головну компанію для поточної компанії користувача"""
        company = self.env.company
        # Якщо поточна компанія є дочірньою, шукаємо головну
        while company.parent_id:
            company = company.parent_id
        return company
    
    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        """Переписуємо метод search для фільтрації за поточною компанією"""
        # Отримуємо головну компанію для поточної компанії
        current_company = self.env.company
        while current_company.parent_id:
            current_company = current_company.parent_id
        
        # Додаємо фільтр за компанією, якщо його ще немає
        if self._context.get('force_company_filter', True):
            company_domain = [('company_id', '=', current_company.id)]
            if not any(arg[0] == 'company_id' for arg in args if isinstance(arg, (tuple, list))):
                args = args + company_domain
        
        return super(StockRegion, self).search(args, offset=offset, limit=limit, order=order, count=count)

    @api.constrains('code')
    def _check_code(self):
        for record in self:
            if not record.code:
                raise ValidationError('Поле "Код" не може бути порожнім.')
            if not re.match(r'^[A-Z]{2}$', record.code):
                raise ValidationError('Код має складатися з двох великих латинських літер (наприклад, KY).')
    
    @api.constrains('code', 'company_id')
    def _check_code_company_unique(self):
        for record in self:
            domain = [
                ('code', '=', record.code),
                ('company_id', '=', record.company_id.id),
                ('id', '!=', record.id)
            ]
            if self.search_count(domain) > 0:
                raise ValidationError(
                    f'Район з кодом "{record.code}" вже існує для компанії "{record.company_id.name}".'
                )
    
    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)', 
         'Код району має бути унікальним в межах компанії!')
    ]