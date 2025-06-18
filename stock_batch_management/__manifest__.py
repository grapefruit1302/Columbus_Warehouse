{
    'name': 'Stock Batch Management',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Партійний облік товарів з FIFO логікою',
    'description': '''
        Модуль для партійного обліку товарів:
        - Автоматичне створення партій при надходженні
        - FIFO логіка списання
        - Трекінг руху партій
        - Звіти по партіях
        - Аналіз руху товарів та залишків
        - Деталізація по складах, локаціях, номенклатурі та партіях
        - Інтеграція з модулями приходу та номенклатури
    ''',
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'stock', 
        'custom_stock_receipt',
        'custom_nomenclature'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/stock_batch_views.xml',
        'views/stock_batch_movement_views.xml',
        'views/product_nomenclature_views.xml',
        'views/stock_receipt_incoming_views.xml',
        'views/stock_batch_report_wizard_views.xml',
        'views/menu_views.xml',
        'reports/stock_batch_report_views.xml',
        'reports/stock_batch_qweb_reports.xml',
        'views/stock_receipt_disposal_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}