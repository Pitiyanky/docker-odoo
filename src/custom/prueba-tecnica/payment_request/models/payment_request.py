# -*- coding: utf-8 -*-
import psycopg2
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError, AccessError

class PaymentRequest(models.Model):
    _name = 'payment.request'
    _description = 'Solicitud de Pago a Proveedor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Referencia', required=True, copy=False, readonly=True, default=lambda self: _('Nuevo'))
    partner_id = fields.Many2one('res.partner', string='Proveedor', required=True, tracking=True)
    requester_id = fields.Many2one('res.users', string='Solicitante', required=True, default=lambda self: self.env.user, readonly=True)
    date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    concept = fields.Text(string='Concepto / Justificación', required=True)
    amount = fields.Monetary(string='Monto', required=True, currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', required=True, default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('to_approve', 'En Aprobación'),
        ('approved', 'Aprobada'),
        ('paid', 'Pagada'),
        ('rejected', 'Rechazada'),
    ], string='Estado', default='draft', required=True, readonly=True, copy=False, tracking=True)

    policy_id = fields.Many2one('payment.approval.policy', string='Política Aplicada', readonly=True, copy=False)
    current_step = fields.Integer(string='Paso Actual', default=0, readonly=True, copy=False)
    total_steps = fields.Integer(string='Pasos Totales', related='policy_id.validation_steps', readonly=True)
    approver_id = fields.Many2one('res.users', string='Aprobador en Turno', readonly=True, copy=False, tracking=True)
    approved_by_id = fields.Many2one('res.users', string='Aprobado Finalmente Por', readonly=True, copy=False)
    approval_date = fields.Datetime(string='Fecha Aprobación Final', readonly=True, copy=False)
    rejection_reason = fields.Text(string='Motivo de Rechazo', readonly=True, copy=False)
    payment_id = fields.Many2one('account.payment', string='Pago Contable Vinculado', readonly=True, copy=False)

    historical_ids = fields.One2many('payment.historical.validation', 'request_id', string='Historial de Aprobaciones', readonly=True)

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("El monto de la solicitud debe ser mayor a cero."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('payment.request') or _('Nuevo')
        return super().create(vals_list)

    def write(self, vals):
        allowed_fields = {
            'state', 'approver_id', 'approved_by_id', 'approval_date', 'current_step',
            'policy_id', 'rejection_reason', 'payment_id', 'message_follower_ids', 'activity_ids'
        }
        for rec in self:
            if rec.state != 'draft' and not self.env.is_superuser():
                modified_fields = set(vals.keys())
                if not modified_fields.issubset(allowed_fields):
                    raise UserError(_("No puede modificar los datos de una solicitud que ya ha sido enviada a aprobación."))
        return super().write(vals)

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Solo se pueden enviar solicitudes en estado Borrador."))

            amount_comp = rec.amount
            if rec.currency_id != rec.company_id.currency_id:
                amount_comp = rec.currency_id._convert(rec.amount, rec.company_id.currency_id, rec.company_id, rec.date)

            domain = [
                ('company_id', '=', rec.company_id.id),
                ('minimum_amount', '<=', amount_comp),
                '|', ('maximum_amount', '=', 0.0), ('maximum_amount', '>=', amount_comp)
            ]
            policy = self.env['payment.approval.policy'].search(domain, order='minimum_amount desc', limit=1)

            if not policy or not policy.line_ids:
                raise UserError(_("No existe una política con pasos configurados para este monto (%s). Contacte a Administración.") % amount_comp)

            first_step = policy.get_step_policy(1)
            rec.write({
                'policy_id': policy.id,
                'current_step': 1,
                'approver_id': first_step.approver_id.id,
                'state': 'to_approve',
            })

            rec.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=first_step.approver_id.id,
                summary=_('Paso 1/%s: Aprobación requerida (%s)') % (policy.validation_steps, first_step.name),
                note=_('Solicitud %s por %s %s para %s.') % (rec.name, rec.amount, rec.currency_id.symbol, rec.partner_id.name)
            )

    def action_approve(self):
        self.ensure_one()

        if self.requester_id == self.env.user and not self.env.is_superuser():
            raise UserError(_("El solicitante no puede aprobar su propia solicitud de pago."))

        is_manager = self.env.user.has_group('payment_request.group_payment_request_manager')
        if self.env.user != self.approver_id and not is_manager:
            raise AccessError(_("El paso actual requiere la aprobación de %s.") % self.approver_id.name)

        # Flush ORM antes del bloqueo en base de datos
        self.flush_recordset()

        try:
            self.env.cr.execute(
                "SELECT id, state, current_step FROM payment_request WHERE id = %s FOR UPDATE NOWAIT",
                [self.id]
            )
            row = self.env.cr.fetchone()
            if not row or row[1] != 'to_approve':
                raise UserError(_("La solicitud ya fue procesada por otro usuario concurrentemente."))
        except psycopg2.OperationalError:
            raise UserError(_("El registro está siendo procesado en otra transacción. Intente de nuevo."))

        policy = self.policy_id
        current_step_policy = policy.get_step_policy(self.current_step)

        self.env['payment.historical.validation'].create({
            'request_id': self.id,
            'user_id': self.env.user.id,
            'step_number': self.current_step,
            'step_name': current_step_policy.name,
            'date': fields.Datetime.now(),
        })

        self.activity_feedback(['mail.mail_activity_data_todo'], feedback=_('Aprobado Paso %s') % self.current_step)
        self.message_post(body=_("Paso %s/%s (%s) aprobado por %s.") % (
            self.current_step, self.total_steps, current_step_policy.name, self.env.user.name
        ))

        if self.current_step < self.total_steps:
            next_step_num = self.current_step + 1
            next_step_policy = policy.get_step_policy(next_step_num)
            self.write({
                'current_step': next_step_num,
                'approver_id': next_step_policy.approver_id.id,
            })
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=next_step_policy.approver_id.id,
                summary=_('Paso %s/%s: Aprobación requerida (%s)') % (self.total_steps, next_step_num, next_step_policy.name),
                note=_('Continuación del flujo de aprobación para %s.') % self.name
            )
        else:
            self.write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'approval_date': fields.Datetime.now(),
            })
            self.message_post(body=_("Flujo de aprobación completado. Lista para Tesorería."))

    def action_reject_wizard(self):
        self.ensure_one()
        return {
            'name': _('Rechazar Solicitud de Pago'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.request.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id},
        }

    def action_pay_wizard(self):
        self.ensure_one()
        if not self.env.user.has_group('payment_request.group_payment_request_treasury'):
            raise AccessError(_("Solo Tesorería o Gerencia puede registrar el pago."))
        return {
            'name': _('Registrar Pago a Proveedor'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.request.pay.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_amount_request': self.amount,
                'default_currency_request_id': self.currency_id.id,
            },
        }
