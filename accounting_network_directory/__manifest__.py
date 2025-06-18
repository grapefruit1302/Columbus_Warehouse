{
    'name': 'Довідник мереж(Бухгалтерія)',
    'version': '1.0',
    'category': 'Administration',
    'summary': 'Довідник мереж для бухгалтерії',
    'description': 'Модуль для управління довідником мереж (Бухгалтерія) в Odoo.',
    'depends': ['base', 'stock_region'],
    'data': [
        'security/accounting_network_security.xml',
        'views/accounting_network_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'application': False,
    'author': 'Петровський Юрій',
}