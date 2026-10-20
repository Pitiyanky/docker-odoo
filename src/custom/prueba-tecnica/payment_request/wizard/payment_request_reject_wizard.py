# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class PaymentRequestRejectWizard(models.TransientModel):
    _name = 'payment.request.reject.wizard'
    _description = 'Asistente de Rechazo de Solicitud'

    request_id = fields.Many2one('payment.request', string='Solicitud', required=True)
    reason = fields.Text(string='Motivo de Rechazo', required=True)

    def action_reject(self):
        self.ensure_one()
        request = self.request_id
        is_manager = self.env.user.has_group('payment_request.group_payment_request_manager')
        if self.env.user != request.approver_id and not is_manager:
            raise UserError(_("No tiene permisos para rechazar esta solicitud en su fase actual."))

        request.write({
            'state': 'rejected',
            'rejection_reason': self.reason,
        })
        request.message_post(
            body=_("Solicitud Rechazada por %s (Paso %s).\nMotivo: %s") % (
                self.env.user.name, request.current_step, self.reason
            )
        )
        request.activity_feedback(['mail.mail_activity_data_todo'], feedback=_('Rechazada: %s') % self.reason)
        return {'type': 'ir.actions.act_window_close'}
