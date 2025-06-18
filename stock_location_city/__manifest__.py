{
    'name': 'Довідник НП/Вулиць',
    'version': '1.0',
    'category': 'Inventory/Inventory',
    'summary': 'Управління населеними пунктами для складів',
    'depends': ['stock', 'base', 'network_directory', 'stock_region', 'district_directory', 'accounting_network_directory'],
    'data': [
        'security/ir.model.access.csv',
        'security/stock_location_city_security.xml',
        'views/stock_location_city_views.xml',
    ],
    'installable': True,
    'application': False,
}