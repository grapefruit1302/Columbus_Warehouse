{
    'name': 'Довідник Мікрорайонів',
    'version': '1.0',
    'category': 'Inventory',
    'summary': 'Довідник Мікрорайонів',
    'description': 'Модуль для управління довідником мікрорайонів',
    'depends': ['base', 'stock_region'],
    'data': [
        'security/district_security.xml',
        'views/district_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}