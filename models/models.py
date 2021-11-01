# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_medicine = fields.Boolean(string="Is Medicine", default=False)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_doctor = fields.Boolean(string="Is Doctor", default=False)
