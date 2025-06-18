{
    'name': 'Custom Nomenclature Stock',
    'version': '1.0',
    'description': """
        Кастомний модуль розроблений для використання в модулі склад для ведення номенклатури товарів.
        Включає роботу з категоріями товарів, товарами, привязкою одиниць вимірювання товару, категорії товару.
    """,
    'category': 'Inventory',
    'author': 'Петровський Юрій',
    'website': 'https://www.facebook.com/profile.php?id=100056059076947',
    'depends': ['stock', 'uom', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/product_nomenclature_sequence.xml',
        'data/barcode_directory_data.xml',
        'views/product_nomenclature_views.xml',
        'views/barcode_directory_views.xml',
        'reports/product_label_report.xml',
        'views/product_label_wizard.xml',
        'reports/product_label_template.xml',
        'views/menu_views.xml',

    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}