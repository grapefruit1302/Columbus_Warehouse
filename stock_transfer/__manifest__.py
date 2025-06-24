{
    'name': 'Переміщення',
    'version': '1.0',
    'category': 'Inventory',
    'summary': 'Модуль для переміщення товарів між складами та працівниками з FIFO логікою',
    'description': """
        Модуль для створення та управління документами переміщення товарів:
        - Переміщення між складами
        - Переміщення між працівниками
        - Переміщення зі складу працівнику
        - Переміщення від працівника на склад
        - Автоматична FIFO логіка вибору партій
        - Показ тільки доступних товарів
        - Контроль залишків при переміщенні
        - Друк документів переміщення
    """,
    'author': 'Петровський Юрій',
    'depends': [
        'base', 
        'stock', 
        'hr', 
        'mail',
        'custom_nomenclature'
        # Не додаємо stock_balance_management тут, щоб уникнути циклічних залежностей
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