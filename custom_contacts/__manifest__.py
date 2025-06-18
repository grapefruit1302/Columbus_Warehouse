{
    'name': 'Custom Contacts',
    'version': '1.0',
    'summary': 'Customizations for Contacts module',
    'depends': ['base', 'contacts'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'data/res_partner_category_data.xml',
    ],
    'installable': True,
    'auto_install': False,
}