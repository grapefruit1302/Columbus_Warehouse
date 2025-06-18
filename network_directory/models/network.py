from odoo import models, fields, api
from odoo.exceptions import ValidationError
from lxml import etree
import logging

_logger = logging.getLogger(__name__)

class Network(models.Model):
    _name = 'network.directory'
    _description = 'Довідник мереж'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Найменування', required=True, tracking=True)
    active = fields.Boolean(string='Активний', default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Компанія',
        required=True,
        default=lambda self: self._get_default_company(),
        tracking=True
    )

    @api.model
    def _get_default_company(self):
        """Повертає першу головну компанію з вибраних користувачем"""
        allowed_company_ids = self.env.context.get('allowed_company_ids', [])
        
        if allowed_company_ids:
            # Шукаємо головні компанії серед дозволених
            allowed_companies = self.env['res.company'].browse(allowed_company_ids)
            main_companies = allowed_companies.filtered(lambda c: not c.parent_id)
            if main_companies:
                return main_companies[0]
        
        # Fallback - поточна головна компанія
        company = self.env.company
        while company.parent_id:
            company = company.parent_id
        return company

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        """Встановлюємо правильний домен для company_id"""
        res = super().fields_view_get(view_id, view_type, toolbar, submenu)

        if view_type in ['form', 'tree', 'list']:
            allowed_company_ids = self.env.context.get('allowed_company_ids', [])
            _logger.info(f"Network.fields_view_get: allowed_company_ids = {allowed_company_ids}")
            
            if allowed_company_ids:
                try:
                    doc = etree.XML(res['arch'])
                    
                    # Знаходимо головні компанії з дозволених
                    allowed_companies = self.env['res.company'].browse(allowed_company_ids)
                    main_companies = allowed_companies.filtered(lambda c: not c.parent_id)
                    _logger.info(f"Network.fields_view_get: main_companies = {main_companies.mapped('name')}")
                    
                    if main_companies:
                        # Формуємо домен: тільки головні + тільки з дозволених
                        domain = [('parent_id', '=', False), ('id', 'in', main_companies.ids)]
                        
                        # Застосовуємо до всіх полів company_id
                        for field_node in doc.xpath("//field[@name='company_id']"):
                            field_node.set('domain', str(domain))
                            field_node.set('options', "{'no_create': True, 'no_create_edit': True}")
                            
                            # Якщо одна компанія - робимо readonly
                            if len(main_companies) == 1:
                                field_node.set('readonly', '1')
                        
                        res['arch'] = etree.tostring(doc, encoding='unicode')
                        _logger.info(f"Network: Applied domain {domain} for company_id")
                        
                except Exception as e:
                    _logger.error(f"Network fields_view_get error: {e}")

        return res

    @api.constrains('name', 'company_id')
    def _check_name_company_unique(self):
        """Унікальність назви в межах компанії"""
        for record in self:
            domain = [
                ('name', '=', record.name),
                ('company_id', '=', record.company_id.id),
                ('id', '!=', record.id)
            ]
            if self.search_count(domain) > 0:
                raise ValidationError(
                    f'Мережа з назвою "{record.name}" вже існує для компанії "{record.company_id.name}".'
                )

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)',
         'Назва мережі має бути унікальною в межах компанії!')
    ]


# КЛЮЧОВА ЧАСТИНА - перехоплення name_search для res.company
class ResCompanyInherit(models.Model):
    _inherit = 'res.company'

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Фільтруємо компанії при пошуку, але враховуємо контекст моделі"""
        _logger.info(f"ResCompany.name_search called: name='{name}', args={args}, context={self.env.context}")
        
        # Отримуємо allowed_company_ids з контексту
        allowed_company_ids = self.env.context.get('allowed_company_ids', [])
        
        # Перевіряємо, чи виклик йде для stock.receipt.incoming
        is_stock_receipt = self.env.context.get('default_model') == 'stock.receipt.incoming'
        
        if allowed_company_ids and not is_stock_receipt:
            allowed_companies = self.env['res.company'].browse(allowed_company_ids)
            main_companies = allowed_companies.filtered(lambda c: not c.parent_id)
            _logger.info(f"ResCompany.name_search: allowed_company_ids={allowed_company_ids}, main_companies={main_companies.mapped('name')}")
            
            if main_companies:
                # Додаємо фільтр до args лише якщо не stock.receipt.incoming
                if args is None:
                    args = []
                
                args = list(args) + [
                    ('parent_id', '=', False),
                    ('id', 'in', main_companies.ids)
                ]
                _logger.info(f"ResCompany.name_search: Modified args = {args}")
        
        return super().name_search(name=name, args=args, operator=operator, limit=limit)