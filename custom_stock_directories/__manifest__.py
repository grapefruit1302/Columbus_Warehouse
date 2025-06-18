# -*- coding: utf-8 -*-
{
    'name': "Пункт меню з довідниками",
    'summary': "Додає меню 'Довідники' до модуля Склад",
   
    'author': "Петровський Юрій",
    'category': 'Inventory',
    'version': '1.0',
    'depends': ['stock', 'base', 'stock_region', 'district_directory', 'accounting_network_directory', 'network_directory', 'currency_directory'],
    'data': [
        'views/stock_custom_directories_menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}