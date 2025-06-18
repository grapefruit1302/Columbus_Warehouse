from odoo import models, fields, api
from odoo.exceptions import ValidationError
from lxml import etree
import logging

_logger = logging.getLogger(__name__)

class AccountingNetwork(models.Model):
    _name = 'accounting.network.directory'
    _description = 'Довідник мереж (Бухгалтерія)'
    _order = 'name'

    name = fields.Char(string='Найменування', required=True)
    active = fields.Boolean(string='Активний', default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Компанія',
        required=True,
        default=lambda self: self._get_default_company()
    )

    @api.model
    def _get_default_company(self):
        """Повертає першу головну компанію з вибраних користувачем"""
        allowed_company_ids = self.env.context.get('allowed_company_ids', [])
        if allowed_company_ids:
            allowed_companies = self.env['res.company'].browse(allowed_company_ids)
            main_companies = allowed_companies.filtered(lambda c: not c.parent_id)
            if main_companies:
                return main_companies[0]
        company = self.env.company
        while company.parent_id:
            company = company.parent_id
        return company

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        """Встановлюємо правильний домен для company_id"""
        res = super().fields_view_get(view_id, view_type, toolbar, submenu)
        if view_type in ['form', 'list']:
            allowed_company_ids = self.env.context.get('allowed_company_ids', [])
            _logger.info(f"AccountingNetwork.fields_view_get: allowed_company_ids = {allowed_company_ids}")
            if allowed_company_ids:
                try:
                    doc = etree.XML(res['arch'])
                    allowed_companies = self.env['res.company'].browse(allowed_company_ids)
                    main_companies = allowed_companies.filtered(lambda c: not c.parent_id)
                    _logger.info(f"AccountingNetwork.fields_view_get: main_companies = {main_companies.mapped('name')}")
                    if main_companies:
                        domain = [('parent_id', '=', False), ('id', 'in', main_companies.ids)]
                        for field_node in doc.xpath("//field[@name='company_id']"):
                            field_node.set('domain', str(domain))
                            field_node.set('options', "{'no_create': True, 'no_create_edit': True}")
                            if len(main_companies) == 1:
                                field_node.set('readonly', '1')
                        res['arch'] = etree.tostring(doc, encoding='unicode')
                        _logger.info(f"AccountingNetwork: Applied domain {domain} for company_id")
                except Exception as e:
                    _logger.error(f"AccountingNetwork fields_view_get error: {e}")
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

class ResCompanyInherit(models.Model):
    _inherit = 'res.company'

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Фільтруємо компанії при пошуку"""
        _logger.info(f"ResCompany.name_search called: name='{name}', args={args}, context={self.env.context}")
        allowed_company_ids = self.env.context.get('allowed_company_ids', [])
        if allowed_company_ids:
            allowed_companies = self.env['res.company'].browse(allowed_company_ids)
            main_companies = allowed_companies.filtered(lambda c: not c.parent_id)
            _logger.info(f"ResCompany.name_search: allowed_company_ids={allowed_company_ids}, main_companies={main_companies.mapped('name')}")
            if main_companies:
                if args is None:
                    args = []
                args = list(args) + [
                    ('parent_id', '=', False),
                    ('id', 'in', main_companies.ids)
                ]
                _logger.info(f"ResCompany.name_search: Modified args = {args}")
        return super().name_search(name=name, args=args, operator=operator, limit=limit)
    


class IrUiMenuInheritAccounting(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _visible_menu_ids(self, debug=False):
        visible_menu_ids = super()._visible_menu_ids(debug=debug)
        current_company_id = self.env.company.id
        
        menu_to_check_xml_id = 'accounting_network.menu_accounting_network_directory' 
        
        try:
            menu_to_check_obj = self.env.ref(menu_to_check_xml_id, raise_if_not_found=False)
        except Exception as e:
            _logger.error(f"Помилка при отриманні меню за XML ID '{menu_to_check_xml_id}': {e}")
            menu_to_check_obj = None

        if not menu_to_check_obj:
            _logger.warning(f"Не вдалося знайти пункт меню за XML ID: {menu_to_check_xml_id}.")
            return list(visible_menu_ids)

        menu_to_check_id = menu_to_check_obj.id
        
        final_visible_menu_ids = set(visible_menu_ids) 
        
        if menu_to_check_id in final_visible_menu_ids:
            # Ось ключова умова:
            if current_company_id != 1: # Якщо поточна компанія НЕ ID=1
                final_visible_menu_ids.remove(menu_to_check_id) # Приховати меню
        
        return list(final_visible_menu_ids)
