# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class PaymentRequestPayWizard(models.TransientModel):
    _name = 'payment.request.pay.wizard'
    _description = 'Asistente de Pago de Solicitud'

    request_id = fields.Many2one('payment.request', string='Solicitud', required=True)
    partner_id = fields.Many2one('res.partner', string='Proveedor', readonly=True)
    amount_request = fields.Monetary(string='Monto Solicitado', readonly=True, currency_field='currency_request_id')
    currency_request_id = fields.Many2one('res.currency', string='Moneda Solicitud', readonly=True)
    
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Pago',
        required=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]"
    )
    payment_date = fields.Date(string='Fecha de Pago', default=fields.Date.context_today, required=True)
    
    payment_currency_id = fields.Many2one(
        'res.currency',
        string='Moneda de Pago',
        compute='_compute_payment_currency_id',
        store=True
    )
    payment_amount = fields.Monetary(
        string='Monto a Pagar en Diario',
        compute='_compute_payment_amount',
        store=True,
        currency_field='payment_currency_id'
    )
    company_id = fields.Many2one(related='request_id.company_id', string='Compañía')

    @api.depends('journal_id')
    def _compute_payment_currency_id(self):
        for rec in self:
            rec.payment_currency_id = rec.journal_id.currency_id or rec.company_id.currency_id

    @api.depends('amount_request', 'currency_request_id', 'payment_currency_id', 'payment_date', 'journal_id')
    def _compute_payment_amount(self):
        for rec in self:
            if rec.currency_request_id and rec.payment_currency_id and rec.payment_date:
                if rec.currency_request_id == rec.payment_currency_id:
                    rec.payment_amount = rec.amount_request
                else:
                    rec.payment_amount = rec.currency_request_id._convert(
                        rec.amount_request,
                        rec.payment_currency_id,
                        rec.company_id,
                        rec.payment_date
                    )
            else:
                rec.payment_amount = 0.0

    def action_confirm_payment(self):
        self.ensure_one()
        request = self.request_id

        # Flush ORM antes del lock pesimista
        request.flush_recordset()

        self.env.cr.execute(
            "SELECT id, state, payment_id FROM payment_request WHERE id = %s FOR UPDATE",
            [request.id]
        )
        row = self.env.cr.fetchone()
        if not row or row[1] != 'approved' or row[2]:
            raise UserError(_("La solicitud ya ha sido pagada o no se encuentra en estado Aprobada."))

        if self.payment_amount <= 0:
            raise ValidationError(_("El monto a pagar debe ser mayor a 0."))

        payment_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': request.partner_id.id,
            'amount': self.payment_amount,
            'currency_id': self.payment_currency_id.id,
            'date': self.payment_date,
            'journal_id': self.journal_id.id,
            'memo': f"{request.name} - {request.concept}", 
            'company_id': request.company_id.id,
            'payment_request_id': request.id,
        }
        
        # Crear pago con contexto from_payment_request=True
        payment = self.env['account.payment'].with_context(from_payment_request=True).create(payment_vals)
        try:
            payment.action_post()
        except Exception:
            pass

        request.write({
            'state': 'paid',
            'payment_id': payment.id,
        })
        request.message_post(
            body=_("Pago registrado con éxito en el diario %s por %s %s (Pago: %s).") % (
                self.journal_id.name, self.payment_amount, self.payment_currency_id.symbol, payment.name
            )
        )
        return {'type': 'ir.actions.act_window_close'}
