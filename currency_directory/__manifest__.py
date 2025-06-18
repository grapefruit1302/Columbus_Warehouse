
{
    'name': 'Довідник валют',
    'version': '1.0',
    'category': 'Inventory/Inventory',
    'summary': 'Довідник валют з історією курсів',
    'description': """
Довідник валют для складської програми
=====================================

Функціональність:
* Управління валютами (назва, коротка назва, кратність, курс)
* Історія змін курсів валют
* Інтеграція з меню Склад->Налаштування
* Можливість використання в інших модулях
    """,
    'author': 'Юрій Петровський',
    'website': 'https://columbus.te.ua',
    'depends': ['base', 'stock', 'mail', 'stock_region'],
    'data': [
        'security/ir.model.access.csv',
        'views/currency_directory_views.xml',
        'data/currency_data.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False, 
    'application': False,
}