{
    'name': 'Управління контактами та постачальниками',
    'version': '1.0',
    'category': 'Contacts',
    'summary': 'Розширення функціональності контактів з додатковими категоріями',
    'description': """
        Цей модуль додає:
        - Галочку "Є постачальником" для контактів
        - Систему категоризації контактів (постачальники, компанії, працівники)
        - Покращені фільтри та групування
    """,
    'author': 'Петровський Юрій',
    'website': 'https://columbus.te.ua/',
    'depends': ['base', 'contacts'],
    'data': [
        'security/ir.model.access.csv',
        'data/contact_category_data.xml',
        'views/res_partner_views.xml',
        'views/contact_category_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}