# -*- coding: utf-8 -*-
{
    'name': "Employee Clinic SIIC",
    'summary': """  Custom Application for Employee Clinic SIIC""",
    'description': """ Employee Clinic SIIC """,
    'author': "SIIC",
    'category': 'Human Resources/Employees',
    'depends': ['base', 'multi_branch', 'hr'],
    'data': [
        # 'security/security.xml',
        # 'security/ir.model.access.csv',
        # 'data/sequence.xml',
        # 'data/ir_cron.xml',
        'views/clinic_menu.xml',
        'views/product_views.xml',
        'views/partner_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
