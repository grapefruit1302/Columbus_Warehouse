{
    'name': 'Регістр накопичення залишків (1С-стиль)',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Єдиний регістр накопичення для обліку залишків товарів за архітектурою 1С',
    'description': '''
        Модуль реалізує архітектуру регістра накопичення 1С:
        - Єдина таблиця stock_balance_register замість окремих партій та залишків
        - Виміри (Измерения): номенклатура, склад, локація, партія, серійний номер, організація  
        - Ресурси (Ресурсы): кількість
        - Реквізити (Реквизиты): тип операції, документ-джерело
        - FIFO логіка через запити до регістра
        - Автоматичне створення партій як вимірів регістра
        - Методи роботи як в 1С: get_balance, get_turnovers, write_record, fifo_consumption
        - Інтеграція з існуючими документами (custom_stock_receipt, stock_transfer)
        - Оборотно-сальдова відомість та звіти по партіях
    ''',
    'author': 'Петровський Юрій',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'stock',
        'custom_nomenclature',
        'custom_stock_receipt',
        'stock_transfer',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_balance_register_views.xml',
        'views/stock_register_reports_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}