{
    'name': 'Переміщення',
    'version': '1.0',
    'category': 'Inventory',
    'summary': 'Модуль для переміщення товарів між складами та працівниками',
    'description': """
        Модуль для створення та управління документами переміщення товарів:
        - Переміщення між складами
        - Переміщення між працівниками
        - Друк документів переміщення
    """,
    'author': 'Петровський Юрій',
    'depends': [
        'base', 
        'stock', 
        'hr', 
        'mail'
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_transfer_views.xml',
        'views/stock_transfer_menu.xml',
        'reports/stock_transfer_report.xml',
        'data/sequence_data.xml',
    ],
    'installable': True,
    'auto_install': False,
}