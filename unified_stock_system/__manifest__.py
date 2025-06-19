{
    'name': 'Централізована система складських залишків',
    'version': '1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Єдина система обліку залишків для всіх складських операцій',
    'description': """
        Централізована система складських залишків
        ==========================================
        
        Цей модуль створює єдину централізовану таблицю складських залишків,
        яка інтегрується з усіма існуючими модулями складу:
        
        Основні можливості:
        ------------------
        * Єдина таблиця залишків для всіх операцій
        * Автоматичне оновлення при проведенні документів
        * Підтримка партійного обліку
        * Підтримка серійних номерів
        * Контроль доступності при переміщеннях
        * Історія рухів товарів
        * Міграція існуючих даних
        
        Інтеграція з модулями:
        ---------------------
        * custom_stock_receipt - прихідні документи
        * stock_transfer - переміщення товарів  
        * stock_balance - звіти по залишках
        * stock_batch_management - управління партіями
        
        Встановлення:
        ------------
        1. Встановити модуль
        2. Запустити міграцію існуючих даних
        3. Перевірити коректність залишків
        
        Автор: Петровський Юрій
        Версія Odoo: 18.0 Community
    """,
    'author': 'Петровський Юрій',
    'depends': [
        'base',
        'stock', 
        'hr',
        'mail',
        'custom_stock_receipt',
        'stock_transfer',
        'stock_balance',
        'stock_batch_management',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_warehouse_inventory_views.xml',
        'data/ir_sequence_data.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
    'external_dependencies': {
        'python': [],
    },
    'pre_init_hook': None,
    'post_init_hook': None,
    'uninstall_hook': None,
}