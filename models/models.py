# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_medicine = fields.Boolean(string="Is Medicine", default=False)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_doctor = fields.Boolean(string="Is Doctor", default=False)


class StockMove(models.Model):
    _inherit = 'stock.move'

    detection_line_id = fields.Many2one('clinic.detection.medicine',
                                        'Detection Order Line', ondelete='set null', index=True, readonly=True)
    created_detection_line_id = fields.Many2one('clinic.detection.medicine',
                                                'Created Detection Order Line', ondelete='set null', readonly=True,
                                                copy=False)
