# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.osv import expression
from odoo.tools.float_utils import float_compare
from odoo.exceptions import AccessError, UserError, ValidationError

AVAILABLE_STATE = [
    ('draft', 'Draft'),
    ('approve', 'Approved'),
    ('deliver', 'Delivered'),
    ('close', 'Closed'),
    ('cancel', 'Cancel'),
]

READONLY_STATES = {
    'approve': [('readonly', True)],
    'deliver': [('readonly', True)],
    'cancel': [('readonly', True)],
}


class ClinicDetection(models.Model):
    _name = 'clinic.detection'
    _rec_name = 'name'
    _description = 'Clinic Detection'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']

    @api.model
    def _default_warehouse_id(self):
        company = self.env.company.id
        warehouse_ids = self.env['stock.warehouse'].search([('company_id', '=', company)], limit=1)
        return warehouse_ids

    name = fields.Char('Name')
    reference = fields.Char(string="Reference", required=False, )
    company_id = fields.Many2one('res.company', 'Company', required=True, index=True, states=READONLY_STATES,
                                 default=lambda self: self.env.company.id)
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

    picking_count = fields.Integer(compute='_compute_picking', string='Picking count', default=0, store=True)
    picking_ids = fields.Many2many('stock.picking', compute='_compute_picking', string='Receptions', copy=False,
                                   store=True)

    @api.model
    def _default_picking_type(self):
        return self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1).clinic_type_id.id

    picking_type_id = fields.Many2one('stock.picking.type', 'Deliver To', states=READONLY_STATES,
                                      required=True, default=_default_picking_type,
                                      domain="['|', ('warehouse_id', '=', False), ('warehouse_id.company_id', '=', company_id)]",
                                      help="This will determine operation type of incoming shipment")
    default_location_dest_id_usage = fields.Selection(related='picking_type_id.default_location_dest_id.usage',
                                                      string='Destination Location Type',
                                                      help="Technical field used to display the Drop Ship Address",
                                                      readonly=True)
    is_shipped = fields.Boolean(compute="_compute_is_shipped")

    @api.depends('detection_medicine.move_ids.returned_move_ids',
                 'detection_medicine.move_ids.state',
                 'detection_medicine.move_ids.picking_id')
    def _compute_picking(self):
        for order in self:
            pickings = self.env['stock.picking']
            for line in order.detection_medicine:
                # We keep a limited scope on purpose. Ideally, we should also use move_orig_ids and
                # do some recursive search, but that could be prohibitive if not done correctly.
                moves = line.move_ids | line.move_ids.mapped('returned_move_ids')
                pickings |= moves.mapped('picking_id')
            order.picking_ids = pickings
            order.picking_count = len(pickings)

    @api.depends('picking_ids', 'picking_ids.state')
    def _compute_is_shipped(self):
        for order in self:
            if order.picking_ids and all([x.state in ['done', 'cancel'] for x in order.picking_ids]):
                order.is_shipped = True
            else:
                order.is_shipped = False

    @api.onchange('picking_type_id')
    def _onchange_picking_type_id(self):
        if self.picking_type_id.default_location_dest_id.usage != 'customer':
            self.dest_address_id = False

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', '|', ('name', operator, name), ('reference', operator, name),
                      ('detection_employee', operator, name)]
        detection_ids = self._search(expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid)
        return models.lazy_name_get(self.browse(detection_ids).with_user(name_get_uid))

    @api.depends('name', 'detection_employee')
    def name_get(self):
        result = []
        for rec in self:
            name = rec.name
            if rec.detection_employee:
                name += ' (' + rec.detection_employee.name + ')'
            result.append((rec.id, name))
        return result

    def unlink(self):
        for rec in self:
            if not rec.state == 'cancel':
                raise UserError(_('In order to delete Clinic Detection, you must cancel it first.'))
        return super(ClinicDetection, self).unlink()

    def action_approve(self):
        self.write({'state': "approve"})

    def action_deliver(self):
        self._create_picking()
        self.write({'state': "deliver"})

    def action_close(self):
        self.write({'state': "close"})

    def action_cancel(self):
        self.write({'state': "cancel"})

    @api.model
    def _prepare_picking(self):
        return {
            'picking_type_id': self.picking_type_id.id,
            'partner_id': self.detection_employee.id,
            'user_id': False,
            'date': self.detection_date,
            'origin': self.name,
            'location_dest_id': self.picking_type_id.default_location_dest_id,
            'location_id': self.picking_type_id.default_location_src_id,
            'company_id': self.company_id.id,
        }

    def _create_picking(self):
        StockPicking = self.env['stock.picking']
        for order in self:
            if any([ptype in ['product', 'consu'] for ptype in order.detection_medicine.mapped('product_id.type')]):
                pickings = order.picking_ids.filtered(lambda x: x.state == 'deliver')
                if not pickings:
                    res = order._prepare_picking()
                    picking = StockPicking.create(res)
                else:
                    picking = pickings[0]
                moves = order.detection_medicine._create_stock_moves(picking)
                moves = moves.filtered(lambda x: x.state not in ('done', 'cancel'))._action_confirm()
                seq = 0
                for move in sorted(moves, key=lambda move: move.date_expected):
                    seq += 5
                    move.sequence = seq
                moves._action_assign()
                picking.message_post_with_view('mail.message_origin_link',
                                               values={'self': picking, 'origin': order},
                                               subtype_id=self.env.ref('mail.mt_note').id)


class ClinicDetectionMedicine(models.Model):
    _name = 'clinic.detection.medicine'
    _rec_name = 'name'
    _description = 'Clinic Detection Medicine'

    detection_id = fields.Many2one('clinic.detection', string='Detection Reference', required=True, ondelete='cascade',
                                   index=True, copy=False)
    name = fields.Text(string='Description', )
    date_order = fields.Datetime(related='detection_id.detection_date', string='Order Date', readonly=True)
    branch_id = fields.Many2one(related='detection_id.branch_id', string="Branch", index=True)
    company_id = fields.Many2one('res.company', related='detection_id.company_id', string='Company', store=True,
                                 readonly=True)
    sequence = fields.Integer(string='Sequence', default=10)
    product_id = fields.Many2one(
        'product.product', string='Product',
        domain="[('is_medicine', '=', True)]",
        change_default=True, ondelete='restrict', check_company=True)  # Unrequired company
    product_template_id = fields.Many2one(
        'product.template', string='Product Template',
        related="product_id.product_tmpl_id", domain=[('is_medicine', '=', True)])
    product_qty = fields.Float(string='Quantity', digits='Product Quantity', required=True, default=1.0)
    product_uom_qty = fields.Float(string='Quantity', digits='Product Unit of Measure', required=True, default=1.0)
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure',
                                  domain="[('category_id', '=', product_uom_category_id)]")
    product_uom_category_id = fields.Many2one(related='product_id.uom_id.category_id', readonly=True)
    qty_delivered = fields.Float('Delivered Quantity', copy=False, compute_sudo=True, store=True,
                                 digits='Product Unit of Measure', compute="_compute_qty_delivered")
    move_ids = fields.One2many('stock.move', 'detection_line_id', string='Detection', readonly=True,
                               ondelete='set null', copy=False)

    def _compute_qty_delivered(self):
        for line in self:
            line.qty_received = 0.0

    @api.onchange('product_id')
    def _product_id_change(self):
        if not self.product_id:
            return
        self.name = self.product_id.name
        self.product_uom = self.product_id.uom_id

    @api.depends('product_uom', 'product_qty', 'product_id.uom_id')
    def _compute_product_uom_qty(self):
        for line in self:
            if line.product_id and line.product_id.uom_id != line.product_uom:
                line.product_uom_qty = line.product_uom._compute_quantity(line.product_qty, line.product_id.uom_id)
            else:
                line.product_uom_qty = line.product_qty

    def _prepare_stock_moves(self, picking):
        """ Prepare the stock moves data for one order line. This function returns a list of
        dictionary ready to be used in stock.move's create()
        """
        self.ensure_one()
        res = []
        if self.product_id.type not in ['product', 'consu']:
            return res
        qty = 0.0
        price_unit = self._get_stock_move_price_unit()
        outgoing_moves, incoming_moves = self._get_outgoing_incoming_moves()
        for move in outgoing_moves:
            qty -= move.product_uom._compute_quantity(move.product_uom_qty, self.product_uom, rounding_method='HALF-UP')
        for move in incoming_moves:
            qty += move.product_uom._compute_quantity(move.product_uom_qty, self.product_uom, rounding_method='HALF-UP')
        description_picking = self.product_id.with_context(
            lang=self.order_id.dest_address_id.lang or self.env.user.lang)._get_description(
            self.order_id.picking_type_id)
        template = {
            # truncate to 2000 to avoid triggering index limit error
            # TODO: remove index in master?
            'name': (self.name or '')[:2000],
            'product_id': self.product_id.id,
            'product_uom': self.product_uom.id,
            'date': self.order_id.date_order,
            'date_expected': self.date_planned,
            'location_id': self.order_id.partner_id.property_stock_supplier.id,
            'location_dest_id': self.order_id._get_destination_location(),
            'picking_id': picking.id,
            'partner_id': self.order_id.dest_address_id.id,
            'move_dest_ids': [(4, x) for x in self.move_dest_ids.ids],
            'state': 'draft',
            'purchase_line_id': self.id,
            'company_id': self.order_id.company_id.id,
            'price_unit': price_unit,
            'picking_type_id': self.order_id.picking_type_id.id,
            'group_id': self.order_id.group_id.id,
            'origin': self.order_id.name,
            'propagate_date': self.propagate_date,
            'propagate_date_minimum_delta': self.propagate_date_minimum_delta,
            'description_picking': description_picking,
            'propagate_cancel': self.propagate_cancel,
            'route_ids': self.order_id.picking_type_id.warehouse_id and [
                (6, 0, [x.id for x in self.order_id.picking_type_id.warehouse_id.route_ids])] or [],
            'warehouse_id': self.order_id.picking_type_id.warehouse_id.id,
        }
        diff_quantity = self.product_qty - qty
        if float_compare(diff_quantity, 0.0, precision_rounding=self.product_uom.rounding) > 0:
            po_line_uom = self.product_uom
            quant_uom = self.product_id.uom_id
            product_uom_qty, product_uom = po_line_uom._adjust_uom_quantities(diff_quantity, quant_uom)
            template['product_uom_qty'] = product_uom_qty
            template['product_uom'] = product_uom.id
            res.append(template)
        return res

    def _create_stock_moves(self, picking):
        values = []
        for line in self.filtered(lambda l: not l.display_type):
            for val in line._prepare_stock_moves(picking):
                values.append(val)
        return self.env['stock.move'].create(values)
