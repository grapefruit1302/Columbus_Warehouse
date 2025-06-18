from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CurrencyDirectory(models.Model):
    _name = 'currency.directory'
    _description = 'Довідник валют'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(
        string='Назва валюти',
        required=True,
        tracking=True,
        help='Повна назва валюти (наприклад: Українська гривня)'
    )
    
    short_name = fields.Char(
        string='Коротка назва',
        required=True,
        size=10,
        tracking=True,
        help='Коротка назва валюти (наприклад: UAH, USD, EUR)'
    )
    
    multiplicity = fields.Integer(
        string='Кратність',
        default=1,
        required=True,
        tracking=True,
        help='Кратність валюти (зазвичай 1, 10, 100 або 1000)'
    )
    
    rate = fields.Float(
        string='Курс',
        digits=(12, 6),
        default=1.0,
        required=True,
        tracking=True,
        help='Курс валюти відносно базової валюти'
    )
    
    active = fields.Boolean(
        string='Активна',
        default=True,
        tracking=True,
        help='Чи активна валюта для використання'
    )
    

    
    rate_history_ids = fields.One2many(
        'currency.directory.rate.history',
        'currency_id',
        string='Історія курсів',
        help='Історія змін курсу валюти'
    )
    
    last_rate_update = fields.Datetime(
        string='Остання зміна курсу',
        compute='_compute_last_rate_update',
        store=True,
        help='Дата і час останньої зміни курсу'
    )
    
    @api.depends('rate_history_ids.date')
    def _compute_last_rate_update(self):
        for record in self:
            if record.rate_history_ids:
                record.last_rate_update = max(record.rate_history_ids.mapped('date'))
            else:
                record.last_rate_update = False
    
    @api.constrains('short_name')
    def _check_short_name_unique(self):
        for record in self:
            domain = [('short_name', '=', record.short_name), ('id', '!=', record.id)]
            if self.search_count(domain) > 0:
                raise ValidationError(_('Коротка назва валюти має бути унікальною!'))
    
    @api.constrains('multiplicity')
    def _check_multiplicity(self):
        for record in self:
            if record.multiplicity <= 0:
                raise ValidationError(_('Кратність повинна бути більшою за нуль!'))
    
    @api.constrains('rate')
    def _check_rate(self):
        for record in self:
            if record.rate <= 0:
                raise ValidationError(_('Курс валюти повинен бути більшим за нуль!'))
    
    def write(self, vals):
        # Якщо змінюється курс то створюємо запис в історії
        if 'rate' in vals:
            for record in self:
                if vals['rate'] != record.rate:
                    self.env['currency.directory.rate.history'].create({
                        'currency_id': record.id,
                        'old_rate': record.rate,
                        'new_rate': vals['rate'],
                        'date': fields.Datetime.now(),
                        'user_id': self.env.user.id,
                    })
        
        result = super().write(vals)
        
        return result
    
    def name_get(self):
        result = []
        for record in self:
            name = f"{record.name} ({record.short_name})"
            result.append((record.id, name))
        return result
    
    @api.model
    def get_current_rate(self, currency_short_name):
        """Метод для отримання поточного курсу валюти за короткою назвою"""
        currency = self.search([('short_name', '=', currency_short_name), ('active', '=', True)], limit=1)
        return currency.rate if currency else 0.0
    
    def action_view_rate_history(self):
        """Дія для перегляду історії курсів"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Історія курсів - {self.name}',
            'res_model': 'currency.directory.rate.history',
            'view_mode': 'list,form',
            'domain': [('currency_id', '=', self.id)],
            'context': {'default_currency_id': self.id},
            'target': 'current',
        }


class CurrencyDirectoryRateHistory(models.Model):
    _name = 'currency.directory.rate.history'
    _description = 'Історія курсів валют'
    _order = 'date desc'
    
    currency_id = fields.Many2one(
        'currency.directory',
        string='Валюта',
        required=True,
        ondelete='cascade'
    )
    
    old_rate = fields.Float(
        string='Старий курс',
        digits=(12, 6),
        required=True
    )
    
    new_rate = fields.Float(
        string='Новий курс',
        digits=(12, 6),
        required=True
    )
    
    date = fields.Datetime(
        string='Дата зміни',
        required=True,
        default=fields.Datetime.now
    )
    
    user_id = fields.Many2one(
        'res.users',
        string='Користувач',
        required=True,
        default=lambda self: self.env.user
    )