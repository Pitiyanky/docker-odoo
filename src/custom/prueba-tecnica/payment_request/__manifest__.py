# -*- coding: utf-8 -*-
{
    'name': 'Solicitudes de Pago a Proveedores',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Purchases',
    'summary': 'Gestión, aprobación secuencial y pago de solicitudes a proveedores',
    'author': 'Binaural Dev',
    'depends': ['base', 'mail', 'account'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/ir_sequence_data.xml',
        'wizard/payment_request_reject_wizard_views.xml',
        'wizard/payment_request_pay_wizard_views.xml',
        'views/payment_approval_policy_views.xml',
        'views/payment_request_views.xml',
        'views/payment_request_menus.xml',
        'report/payment_request_report.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
