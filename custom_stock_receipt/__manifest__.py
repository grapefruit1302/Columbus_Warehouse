{
    'name': 'Прихідні накладні',
    'version': '18.0.1.0.0',
    'category': 'Warehouse Management',
    'summary': 'Модуль для роботи з прихідними накладними',
    'description': '''
        Модуль для роботи з прихідними накладними з інтеграцією номенклатури товарів.
        
        Функціональність:
        - Створення прихідних накладних
        - Вибір компанії та філії
        - Інтеграція з номенклатурою товарів
        - Розрахунок цін з та без ПДВ
        - Workflow документів
        - Chatter для комунікації
    ''',
    'author': 'Петровський Юрій',
    'website': 'https://www.facebook.com/profile.php?id=100056059076947',
    'depends': [
        'base',
        'stock',
        'product',
        'mail',
        'web',
        'network_directory', 
        'district_directory', 
        'accounting_network_directory',  
        'custom_nomenclature', 
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/stock_receipt_views.xml',
        'views/stock_receipt_incoming_views.xml',
        'views/stock_receipt_disposal_views.xml',
        'views/stock_receipt_return_views.xml',
        'views/stock_receipt_serial_wizard_views.xml',
        'views/report_templates_incoming.xml',
        'views/menu_views.xml',
        'views/stock_disposal_serial_wizard_views.xml',
        'views/report_templates_disposal.xml',
    ],
    'external_dependencies': {
            'python': ['openpyxl', 'xlrd'],  
        },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}