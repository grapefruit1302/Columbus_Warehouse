{
    'name': 'Довідник мереж (Ромсат)',
    'version': '1.0.0',
    'category': 'Inventory',
    'summary': 'Управління мережами складів',
    'description': """
        Модуль для управління мережами складів з прив'язкою до компанії.
        
        Функціональність:
        - Довідник мереж
        - Прив'язка до компанії
        - Фільтрація за компанією
        - Активність мережі
    """,
    'author': 'Юрій Петровський',
    'depends': ['base', 'stock', 'mail', 'stock_region'],
    'data': [
        'security/ir.model.access.csv',
        'security/network_security.xml',
        'views/network_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}