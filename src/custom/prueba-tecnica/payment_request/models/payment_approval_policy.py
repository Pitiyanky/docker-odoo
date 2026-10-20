# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class PaymentApprovalPolicy(models.Model):
    _name = 'payment.approval.policy'
    _description = 'Política de Aprobación de Pagos'
    _order = 'minimum_amount asc'

    name = fields.Char(string='Nombre de la Política', required=True)
    minimum_amount = fields.Monetary(string='Monto Mínimo', required=True, currency_field='currency_id')
    maximum_amount = fields.Monetary(string='Monto Máximo (0 = sin límite)', default=0.0, currency_field='currency_id')
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')
    line_ids = fields.One2many('payment.approval.policy.line', 'policy_id', string='Pasos de Aprobación')
    validation_steps = fields.Integer(string='Pasos Totales', compute='_compute_validation_steps', store=True)

    @api.depends('line_ids')
    def _compute_validation_steps(self):
        for rec in self:
            rec.validation_steps = len(rec.line_ids)

    def get_step_policy(self, step_number):
        self.ensure_one()
        sorted_lines = self.line_ids.sorted('sequence')
        if 1 <= step_number <= len(sorted_lines):
            return sorted_lines[step_number - 1]
        return self.env['payment.approval.policy.line']


class PaymentApprovalPolicyLine(models.Model):
    _name = 'payment.approval.policy.line'
    _description = 'Línea de Paso de Aprobación'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Paso / Secuencia', default=1, required=True)
    policy_id = fields.Many2one('payment.approval.policy', string='Política', ondelete='cascade', required=True)
    name = fields.Char(string='Rol / Etiqueta del Paso', required=True, help="Ej. Jefe de Área, Gerencia General")
    approver_id = fields.Many2one('res.users', string='Usuario Aprobador', required=True, ondelete='restrict')
