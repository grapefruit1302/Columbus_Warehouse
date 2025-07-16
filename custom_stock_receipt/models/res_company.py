from odoo import models, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        # Перевіряємо, чи виклик походить із вашої моделі
        if self.env.context.get('from_stock_receipt_incoming'):
            # Використовуємо ваш домен без додаткових модифікацій
            args = args or []
            child_company_ids = []
            allowed_companies = self.env.context.get('allowed_company_ids', [])
            if allowed_companies:
                companies = self.env['res.company'].browse(allowed_companies)
            else:
                companies = self.env.company
            
            for company in companies:
                child_company_ids.extend(company.child_ids.ids)
            
            if child_company_ids:
                args = [('id', 'in', child_company_ids)] + args
            else:
                args = [('id', '=', False)]
            
            return super(ResCompany, self).name_search(name=name, args=args, operator=operator, limit=limit)
        
        # Для інши випадків викликаємо стандартний name_search
        return super(ResCompany, self).name_search(name=name, args=args, operator=operator, limit=limit)