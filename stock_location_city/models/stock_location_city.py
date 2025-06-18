from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class StockLocationCity(models.Model):
    _name = 'stock.location.city'
    _description = 'Населений пункт'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(string='Назва', required=True, tracking=True)
    network_id = fields.Many2one(
        'network.directory',
        string='Мережа',
        tracking=True
    )
    region_id = fields.Many2one(
        'stock.region',
        string='Район',
        tracking=True
    )
    district_id = fields.Many2one(
        'district.directory',
        string='Мікрорайон',
        tracking=True
    )
    accounting_network_id = fields.Many2one(
        'accounting.network.directory',
        string='Мережа (Бухгалтерія)',
        tracking=True
    )
    active = fields.Boolean(string='Активний', default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Компанія',
        required=True,
        default=lambda self: self.env.company,
        tracking=True
    )

    @api.constrains('name', 'network_id', 'region_id', 'district_id', 'accounting_network_id', 'company_id')
    def _check_unique(self):
        for record in self:
            domain = [
                ('name', '=', record.name),
                ('network_id', '=', record.network_id.id if record.network_id else False),
                ('region_id', '=', record.region_id.id if record.region_id else False),
                ('district_id', '=', record.district_id.id if record.district_id else False),
                ('accounting_network_id', '=', record.accounting_network_id.id if record.accounting_network_id else False),
                ('company_id', '=', record.company_id.id),
                ('id', '!=', record.id)
            ]
            if self.search_count(domain) > 0:
                raise ValidationError(
                    f'Населений пункт "{record.name}" уже існує для мережі '
                    f'"{record.network_id.name if record.network_id else "без мережі"}", '
                    f'району "{record.region_id.name if record.region_id else "без району"}", '
                    f'мікрорайону "{record.district_id.name if record.district_id else "без мікрорайону"}", '
                    f'мережі (бухгалтерія) "{record.accounting_network_id.name if record.accounting_network_id else "без мережі"}" '
                    f'компанії "{record.company_id.name}".'
                )

    @api.constrains('network_id', 'region_id', 'district_id', 'accounting_network_id', 'company_id')
    def _check_same_company(self):
        """Перевіряємо, що всі пов'язані записи належать до тієї ж компанії"""
        for record in self:
            if record.network_id and record.network_id.company_id != record.company_id:
                raise ValidationError(
                    f'Мережа "{record.network_id.name}" належить компанії "{record.network_id.company_id.name}", '
                    f'але населений пункт належить компанії "{record.company_id.name}".')
            if record.region_id and record.region_id.company_id != record.company_id:
                raise ValidationError(
                    f'Район "{record.region_id.name}" належить компанії "{record.region_id.company_id.name}", '
                    f'але населений пункт належить компанії "{record.company_id.name}".')
            if record.district_id and record.district_id.company_id != record.company_id:
                raise ValidationError(
                    f'Мікрорайон "{record.district_id.name}" належить компанії "{record.district_id.company_id.name}", '
                    f'але населений пункт належить компанії "{record.company_id.name}".')
            if record.accounting_network_id and record.accounting_network_id.company_id != record.company_id:
                raise ValidationError(
                    f'Мережа (Бухгалтерія) "{record.accounting_network_id.name}" належить компанії '
                    f'"{record.accounting_network_id.company_id.name}", але населений пункт належить компанії '
                    f'"{record.company_id.name}".')

    @api.onchange('company_id')
    def _onchange_company_id(self):
        """Оновлюємо домени для полів при зміні компанії"""
        selected_companies = self.env.companies.ids
        _logger.info(f"Selected companies from UI: {selected_companies}")
        if not self.company_id:
            self.network_id = False
            self.region_id = False
            self.district_id = False
            self.accounting_network_id = False
            return {
                'domain': {
                    'network_id': [],
                    'region_id': [],
                    'district_id': [],
                    'accounting_network_id': []
                }
            }

        domain = {
            'network_id': [('company_id', '=', self.company_id.id)],
            'region_id': [('company_id', '=', self.company_id.id)],
            'district_id': [('company_id', '=', self.company_id.id)],
            'accounting_network_id': [('company_id', '=', self.company_id.id)]
        }

        # Скидаємо значення, якщо вони не відповідають компанії
        if self.network_id and self.network_id.company_id != self.company_id:
            self.network_id = False
        if self.region_id and self.region_id.company_id != self.company_id:
            self.region_id = False
        if self.district_id and self.district_id.company_id != self.company_id:
            self.district_id = False
        if self.accounting_network_id and self.accounting_network_id.company_id != self.company_id:
            self.accounting_network_id = False

        _logger.info(f"Domain set for company ID {self.company_id.id}: {domain}")
        return {'domain': domain}

    def name_get(self):
        """Відображення назви з додатковою інформацією"""
        result = []
        for record in self:
            name = record.name
            if record.region_id:
                name = f"{name} ({record.region_id.code})"
            result.append((record.id, name))
        return result

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100):
        """Пошук за назвою або кодом району"""
        args = args or []
        if name:
            args = ['|', ('name', operator, name), ('region_id.code', operator, name)] + args
        _logger.info(f"Search args for stock.location.city: {args}")
        return self._search(args, limit=limit)

    _sql_constraints = [
        ('unique', 'unique(name, network_id, region_id, district_id, accounting_network_id, company_id)',
         'Комбінація назви, мережі, району, мікрорайону, мережі (бухгалтерія) та компанії має бути унікальною!')
    ]