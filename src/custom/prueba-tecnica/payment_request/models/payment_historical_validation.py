# -*- coding: utf-8 -*-
from odoo import fields, models

class PaymentHistoricalValidation(models.Model):
    _name = 'payment.historical.validation'
    _description = 'Historial de Validaciones de Pago'
    _order = 'date desc, id desc'

    request_id = fields.Many2one('payment.request', string='Solicitud de Pago', required=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', string='Aprobado Por', required=True)
    step_number = fields.Integer(string='Nro. de Paso')
    step_name = fields.Char(string='Fase / Nivel')
    date = fields.Datetime(string='Fecha y Hora', default=fields.Datetime.now, required=True)
