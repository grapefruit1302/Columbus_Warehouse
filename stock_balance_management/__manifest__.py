{
    'name': 'Управління залишками',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Централізована система обліку залишків товарів',
    'description': '''
        Модуль для централізованого обліку залишків товарів:
        - Облік залишків по складах, локаціях, партіях та працівниках
        - Переміщення між складами та працівниками
        - Перевірка доступності при операціях
        - Автоматичне оновлення залишків
        - Звіти по залишках
        - Інтеграція з партійним обліком
        - FIFO логіка списання
        - Облік товарів у працівників
        - РОЗШИРЕНИЙ облік серійних номерів з детальним управлінням
        - Візуальні індикатори неповних серійних номерів
        - Імпорт серійних номерів з Excel
    ''',
    'author': 'Петровський Юрій',
    'depends': [
        'base',
        'stock',
        'custom_nomenclature',
        'stock_batch_management',
        'stock_transfer',
        'custom_stock_receipt'
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_balance_views.xml',  # ОНОВЛЕНИЙ
        'views/stock_balance_wizard_views.xml',
        'views/stock_balance_serial_wizard_views.xml',
        'views/stock_balance_serial_detailed_wizard_views.xml',  # НОВИЙ
        'views/menu_views.xml',
        'reports/stock_balance_reports.xml',
    ],
    'external_dependencies': {
        'python': ['openpyxl', 'xlrd'],  # Для імпорту Excel файлів
    },
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}