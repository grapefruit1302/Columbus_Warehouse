{
    'name': 'Звіти по залишках товарів',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Звіти по залишках товарів з партійним обліком та FIFO',
    'description': """
Модуль для формування звітів по залишках товарів:
- Звіт по залишках товарів на складах
- Партійний облік товарів
- Принцип FIFO
- Фільтрація по компаніях, складах, категоріях
- Друк звітів
    """,
    'author': 'Custom Development',
    'website': '',
    'depends': ['base', 'stock', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_balance_views.xml',
        'views/menu_views.xml',
        'reports/stock_balance_report_template.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}