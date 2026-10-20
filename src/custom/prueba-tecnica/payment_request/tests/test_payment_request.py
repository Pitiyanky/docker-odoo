# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError, AccessError

class TestPaymentRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company

        # Campo Many2many en Odoo 19: group_ids
        group_field = 'group_ids' if 'group_ids' in cls.env['res.users']._fields else 'groups_id'

        cls.grp_requester = cls.env.ref('payment_request.group_payment_request_requester')
        cls.grp_approver = cls.env.ref('payment_request.group_payment_request_approver')
        cls.grp_treasury = cls.env.ref('payment_request.group_payment_request_treasury')

        cls.user_requester = cls.env['res.users'].create({
            'name': 'Juan Solicitante',
            'login': 'juan_solicitante',
            'email': 'juan@test.com',
            group_field: [(6, 0, [cls.grp_requester.id])],
            'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id])],
        })

        cls.user_approver = cls.env['res.users'].create({
            'name': 'Pedro Aprobador',
            'login': 'pedro_aprobador',
            'email': 'pedro@test.com',
            group_field: [(6, 0, [cls.grp_approver.id])],
            'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id])],
        })

        cls.user_other_approver = cls.env['res.users'].create({
            'name': 'Carlos Gerente',
            'login': 'carlos_gerente',
            'email': 'carlos@test.com',
            group_field: [(6, 0, [cls.grp_approver.id])],
            'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id])],
        })

        cls.partner = cls.env['res.partner'].create({
            'name': 'Distribuidora Central C.A.',
            'supplier_rank': 1,
        })

        # Política base con 1 paso
        cls.policy_base = cls.env['payment.approval.policy'].create({
            'name': 'Política Base',
            'minimum_amount': 0.0,
            'maximum_amount': 0.0,
            'company_id': cls.company_a.id,
            'line_ids': [
                (0, 0, {'sequence': 1, 'name': 'Aprobación Base', 'approver_id': cls.user_approver.id})
            ]
        })

    def test_01_amount_positive_constraint(self):
        with self.assertRaises(ValidationError):
            self.env['payment.request'].create({
                'partner_id': self.partner.id,
                'amount': 0.0,
                'concept': 'Monto inválido',
            })

    def test_02_requester_cannot_approve(self):
        req = self.env['payment.request'].with_user(self.user_requester).create({
            'partner_id': self.partner.id,
            'amount': 100.0,
            'concept': 'Material de oficina',
        })
        req.action_submit()
        self.assertEqual(req.state, 'to_approve')

        with self.assertRaises(UserError):
            req.with_user(self.user_requester).action_approve()

    def test_03_sent_request_cannot_be_edited(self):
        req = self.env['payment.request'].with_user(self.user_requester).create({
            'partner_id': self.partner.id,
            'amount': 150.0,
            'concept': 'Servicio técnico',
        })
        req.action_submit()
        self.assertEqual(req.state, 'to_approve')

        with self.assertRaises(UserError):
            req.with_user(self.user_requester).write({'amount': 250.0})

    def test_04_only_assigned_approver_can_approve(self):
        req = self.env['payment.request'].create({
            'partner_id': self.partner.id,
            'amount': 200.0,
            'concept': 'Pago de servicios',
        })
        req.action_submit()
        self.assertEqual(req.approver_id, self.user_approver)

        with self.assertRaises(AccessError):
            req.with_user(self.user_other_approver).action_approve()

        req.with_user(self.user_approver).action_approve()
        self.assertEqual(req.state, 'approved')
        self.assertEqual(req.approved_by_id, self.user_approver)

    def test_05_rejection_wizard_posts_to_chatter(self):
        req = self.env['payment.request'].create({
            'partner_id': self.partner.id,
            'amount': 300.0,
            'concept': 'Gasto no justificado',
        })
        req.action_submit()

        wizard = self.env['payment.request.reject.wizard'].with_user(self.user_approver).create({
            'request_id': req.id,
            'reason': 'Factura no adjunta en el expediente',
        })
        wizard.action_reject()

        self.assertEqual(req.state, 'rejected')
        self.assertEqual(req.rejection_reason, 'Factura no adjunta en el expediente')
        messages = req.message_ids.mapped('body')
        self.assertTrue(any('Factura no adjunta en el expediente' in msg for msg in messages))

    def test_06_double_payment_prevention(self):
        req = self.env['payment.request'].create({
            'partner_id': self.partner.id,
            'amount': 100.0,
            'concept': 'Anticipo proveedor',
        })
        req.action_submit()
        req.with_user(self.user_approver).action_approve()

        journal = self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', self.company_a.id)
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].create({
                'name': 'Banco Test',
                'type': 'bank',
                'code': 'BNKT',
                'company_id': self.company_a.id,
            })

        pay_wizard = self.env['payment.request.pay.wizard'].create({
            'request_id': req.id,
            'journal_id': journal.id,
            'payment_date': '2026-10-20',
        })
        pay_wizard.action_confirm_payment()
        self.assertEqual(req.state, 'paid')
        self.assertTrue(req.payment_id)

        pay_wizard_duplicate = self.env['payment.request.pay.wizard'].create({
            'request_id': req.id,
            'journal_id': journal.id,
            'payment_date': '2026-10-20',
        })
        with self.assertRaises(UserError):
            pay_wizard_duplicate.action_confirm_payment()

    def test_07_multicompany_isolation(self):
        company_b = self.env['res.company'].create({'name': 'Compañía B C.A.'})
        group_field = 'group_ids' if 'group_ids' in self.env['res.users']._fields else 'groups_id'
        
        user_comp_b = self.env['res.users'].create({
            'name': 'Usuario Comp B',
            'login': 'user_b',
            group_field: [(6, 0, [self.grp_requester.id])],
            'company_id': company_b.id,
            'company_ids': [(6, 0, [company_b.id])],
        })

        req_a = self.env['payment.request'].create({
            'partner_id': self.partner.id,
            'amount': 400.0,
            'concept': 'Gasto interno Compañía A',
            'company_id': self.company_a.id,
        })

        requests_visible = self.env['payment.request'].with_user(user_comp_b).search([('id', '=', req_a.id)])
        self.assertFalse(requests_visible)

    def test_08_multi_step_sequential_approval(self):
        """Verifica que la solicitud pase por todos los pasos antes de quedar Aprobada."""
        policy_multi = self.env['payment.approval.policy'].create({
            'name': 'Doble Aprobación Especial',
            'minimum_amount': 500.0,
            'maximum_amount': 0.0,
            'company_id': self.company_a.id,
            'line_ids': [
                (0, 0, {'sequence': 1, 'name': 'Paso 1: Jefe Área', 'approver_id': self.user_approver.id}),
                (0, 0, {'sequence': 2, 'name': 'Paso 2: Gerencia', 'approver_id': self.user_other_approver.id}),
            ]
        })

        req = self.env['payment.request'].create({
            'partner_id': self.partner.id,
            'amount': 600.0,
            'concept': 'Compra mayor con dos aprobaciones',
        })
        req.action_submit()
        self.assertEqual(req.current_step, 1)
        self.assertEqual(req.approver_id, self.user_approver)
        self.assertEqual(req.state, 'to_approve')

        # Paso 1: Aprueba user_approver
        req.with_user(self.user_approver).action_approve()
        self.assertEqual(req.current_step, 2)
        self.assertEqual(req.approver_id, self.user_other_approver)
        self.assertEqual(req.state, 'to_approve')

        # Paso 2: Aprueba user_other_approver
        req.with_user(self.user_other_approver).action_approve()
        self.assertEqual(req.state, 'approved')
        self.assertEqual(len(req.historical_ids), 2)

    def test_09_block_direct_accounting_payment_creation(self):
        """Verifica que no se puedan crear pagos directos a proveedores en Contabilidad."""
        journal = self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', self.company_a.id)
        ], limit=1)

        with self.assertRaises(AccessError):
            self.env['account.payment'].with_user(self.user_requester).create({
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'partner_id': self.partner.id,
                'amount': 500.0,
                'journal_id': journal.id,
            })
