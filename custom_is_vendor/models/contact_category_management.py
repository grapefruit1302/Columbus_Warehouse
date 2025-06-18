from odoo import api, fields, models

class ContactCategory(models.Model):
    _name = 'contact.category'
    _description = 'Категорія контакту'
    _order = 'sequence, name'

    name = fields.Char(string='Назва категорії', required=True, translate=True)
    code = fields.Char(string='Код категорії', required=True, help='Унікальний код для використання в коді')
    sequence = fields.Integer(string='Порядок', default=10, help='Порядок відображення категорії')

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Код категорії має бути унікальним!')
    ]