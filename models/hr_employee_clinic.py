# -*- coding: utf-8 -*-

from odoo import models, fields, api

AVAILABLE_STATE = [
    ('draft', 'Draft'),
    ('close', 'Closed'),
    ('cancel', 'Cancel'),
]


class ClinicDetection(models.Model):
    _name = 'clinic.detection'
    _rec_name = 'name'
    _description = 'Clinic Detection'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']

    name = fields.Char('Name')
    reference = fields.Char(string="Reference", required=False, )
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.uid, index=True,
                              tracking=True)
    branch_id = fields.Many2one(comodel_name="res.branch", string="Branch", required=True,
                                index=True, help='This is branch to set')
    detection_date = fields.Datetime(string='Detection Date', required=True, index=True, copy=False,
                                     default=fields.Datetime.now, )

    detection_medicine = fields.One2many('clinic.detection.medicine', 'detection_id', string='Order Parts', copy=True,
                                         auto_join=True)
    detection_notes = fields.Html('Notes', help='Notes')
    detection_doctor = fields.Many2one('res.partner', string='Doctor',
                                       domain="[('is_doctor', '=', True)]",
                                       auto_join=True, tracking=True, required=True)
    detection_employee = fields.Many2one('hr.employee', string='Employee', auto_join=True, tracking=True, required=True)
    state = fields.Selection(AVAILABLE_STATE, string='State', index=True, default=AVAILABLE_STATE[0][0],
                             tracking=True, )

    @api.model
    def create(self, values):
        res = super(ClinicDetection, self).create(values)
        res.name = self.env['ir.sequence'].next_by_code('clinic.detection') or '/'
        return res


class ClinicDetectionMedicine(models.Model):
    _name = 'clinic.detection.medicine'
    _rec_name = 'name'
    _description = 'Clinic Detection Medicine'

    detection_id = fields.Many2one('clinic.detection', string='Detection Reference', required=True, ondelete='cascade',
                                   index=True, copy=False)
    name = fields.Text(string='Description', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    product_id = fields.Many2one(
        'product.product', string='Product',
        domain="[('is_medicine', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        change_default=True, ondelete='restrict', check_company=True)  # Unrequired company
    product_template_id = fields.Many2one(
        'product.template', string='Product Template',
        related="product_id.product_tmpl_id", domain=[('is_medicine', '=', True)])
    product_uom_qty = fields.Float(string='Quantity', digits='Product Unit of Measure', required=True, default=1.0)
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure',
                                  domain="[('category_id', '=', product_uom_category_id)]")
    product_uom_category_id = fields.Many2one(related='product_id.uom_id.category_id', readonly=True)
    qty_delivered = fields.Float('Delivered Quantity', copy=False, compute_sudo=True, store=True,
                                 digits='Product Unit of Measure', default=0.0)
