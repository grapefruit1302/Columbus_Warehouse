{
    'name': 'Довідник Районів',
    'version': '1.0',
    'summary': 'Довідник районів для управління складом',
    'description': 'Довідник для управління районами з кодом та найменуванням у налаштуваннях складу.',
    'category': 'Inventory',
    'author': 'Петровський Юрій',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/region_views.xml',
        'security/stock_region_security.xml',
    ],
    'installable': True,
    'application': False,
}