# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    payment_request_id = fields.Many2one(
        'payment.request',
        string="Solicitud de Pago Origen",
        readonly=True,
        copy=False
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            payment_type = vals.get('payment_type')
            partner_type = vals.get('partner_type')

            if payment_type == 'outbound' and partner_type == 'supplier':
                is_from_wizard = self.env.context.get('from_payment_request') or vals.get('payment_request_id')
                is_manager = self.env.user.has_group('payment_request.group_payment_request_manager')

                if not is_from_wizard and not is_manager and not self.env.is_superuser():
                    raise AccessError(_(
                        "POLÍTICA DE CONTROL: Está bloqueada la creación manual directa de pagos a proveedores desde Contabilidad.\n"
                        "Todo desembolso debe iniciarse desde una 'Solicitud de Pago' debidamente aprobada o ser ejecutado por Gerencia."
                    ))
        return super().create(vals_list)
