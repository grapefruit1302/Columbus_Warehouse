from odoo import models, api
from .utils import get_document_context_key
import logging

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        context = self.env.context
        
        # Перевіряємо контекст для фільтрації дочірніх компаній
        context_key = context.get('_get_child_companies_domain', '')
        
        # Список моделей, які потребують фільтрації дочірніх компаній
        supported_models = [
            'stock.receipt.incoming',
            'stock.receipt.disposal',
            'stock.receipt.return'
        ]
        
        # Перевіряємо, чи виклик походить від підтримуваної моделі
        if any(model in context_key for model in supported_models):
            _logger.info(f"Custom name_search triggered for context: {context_key}")
            
            # Отримуємо компанії з контексту
            allowed_company_ids = context.get('allowed_company_ids', [])
            child_company_ids = set()
            
            if allowed_company_ids:
                companies = self.browse(allowed_company_ids)
                for company in companies:
                    child_company_ids.update(company.child_ids.ids)
            else:
                child_company_ids.update(self.env.company.child_ids.ids)
            
            # Формуємо домен тільки для дочірніх компаній
            domain = [('id', 'in', list(child_company_ids))] if child_company_ids else [('id', '=', False)]
            if name:
                domain += ['|', ('name', operator, name), ('display_name', operator, name)]
            
            _logger.info(f"Custom name_search domain: {domain}")
            # Виконуємо пошук і повертаємо список кортежів (id, name)
            companies = self.search(domain + args, limit=limit)
            return [(company.id, company.display_name) for company in companies]
        
        # Підтримуємо старий контекст для зворотної сумісності
        if context.get('from_stock_receipt_incoming'):
            _logger.info("Legacy context 'from_stock_receipt_incoming' detected")
            child_company_ids = []
            allowed_companies = context.get('allowed_company_ids', [])
            if allowed_companies:
                companies = self.browse(allowed_companies)
            else:
                companies = self.env.company
            
            for company in companies:
                child_company_ids.extend(company.child_ids.ids)
            
            if child_company_ids:
                args = [('id', 'in', child_company_ids)] + args
            else:
                args = [('id', '=', False)]
            
            return super(ResCompany, self).name_search(name=name, args=args, operator=operator, limit=limit)
        
        # Для інших випадків викликаємо стандартну логіку
        _logger.info("Falling back to super name_search")
        return super(ResCompany, self).name_search(name=name, args=args, operator=operator, limit=limit)