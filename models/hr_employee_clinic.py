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
    picking_ids = fields.many2many('stock.picking', compute='_compute_picking', string='Deliveries', copy=False,
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
        StockWarehouse = self.env['stock.warehouse']

        if (not self.picking_type_id) or (not self.picking_type_id.default_location_dest_id):
            customerloc, supplierloc = StockWarehouse._get_partner_locations()
            destination_id = customerloc.id
        else:
            destination_id = self.picking_type_id.default_location_dest_id.id

        return {
            'picking_type_id': self.picking_type_id.id,
            'partner_id': self.user_id.partner_id.id,
            'user_id': False,
            'date': self.detection_date,
            'origin': self.name,
            'location_dest_id': destination_id,
            'location_id': self.picking_type_id.default_location_src_id.id,
            'company_id': self.company_id.id,
        }

    def _create_picking(self):
        StockPicking = self.env['stock.picking']
        for order in self:
            if any([ptype in ['product', 'consu'] for ptype in order.detection_medicine.mapped('product_id.type')]):
                pickings = order.picking_ids.filtered(lambda x: x.state not in ('done', 'cancel'))
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
        return True

    def action_view_picking(self):
        """ This function returns an action that display existing picking orders of given purchase order ids. When only one found, show the picking immediately.
        """
        action = self.env.ref('stock.action_picking_tree_all')
        result = action.read()[0]
        # override the context to get rid of the default filtering on operation type
        result['context'] = {'default_picking_type_id': self.picking_type_id.id}
        pick_ids = self.mapped('picking_ids')
        # choose the view_mode accordingly
        if not pick_ids or len(pick_ids) > 1:
            result['domain'] = "[('id','in',%s)]" % (pick_ids.ids)
        elif len(pick_ids) == 1:
            res = self.env.ref('stock.view_picking_form', False)
            form_view = [(res and res.id or False, 'form')]
            if 'views' in result:
                result['views'] = form_view + [(state, view) for state, view in result['views'] if view != 'form']
            else:
                result['views'] = form_view
            result['res_id'] = pick_ids.id
        return result


class ClinicDetectionMedicine(models.Model):
    _name = 'clinic.detection.medicine'
    _rec_name = 'name'
    _description = 'Clinic Detection Medicine'

    detection_id = fields.Many2one('clinic.detection', string='Detection Reference', required=True, ondelete='cascade',
                                   index=True, copy=False)
    name = fields.Text(string='Description', )
    detection_date = fields.Datetime(related='detection_id.detection_date', string='Order Date', readonly=True)
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
    qty_to_deliver = fields.Float(string="Qty Remain", compute='_compute_qty_to_deliver', store=True)
    move_ids = fields.One2many('stock.move', 'detection_line_id', string='Detection', readonly=True,
                               ondelete='set null', copy=False)
    move_dest_ids = fields.One2many('stock.move', 'created_detection_line_id', 'Detection Moves')

    display_type = fields.Selection([
        ('line_section', "Section"),
        ('line_note', "Note")], default=False, help="Technical field for UX purpose.")

    @api.depends('move_ids.state', 'move_ids.scrapped', 'move_ids.product_uom_qty', 'move_ids.product_uom')
    def _compute_qty_delivered(self):
        for line in self:  # TODO: maybe one day, this should be done in SQL for performance sake
            qty = 0.0
            outgoing_moves = self.env['stock.move']
            for move in outgoing_moves:
                if move.state != 'done':
                    continue
                qty += move.product_uom._compute_quantity(move.product_uom_qty, line.product_uom,
                                                          rounding_method='HALF-UP')
            line.qty_delivered = qty

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
        template = {
            # truncate to 2000 to avoid triggering index limit error
            # TODO: remove index in master?
            'name': (self.name or '')[:2000],
            'product_id': self.product_id.id,
            'product_uom': self.product_uom.id,
            'date': self.detection_date,
            'location_id': self.detection_id.picking_type_id.default_location_src_id.id,
            'location_dest_id': self.detection_id.picking_type_id.default_location_dest_id.id,
            'picking_id': picking.id,
            'partner_id': self.detection_id.user_id.partner_id.id,
            'move_dest_ids': [(4, x) for x in self.move_dest_ids.ids],
            'state': 'draft',
            'detection_line_id': self.id,
            'company_id': self.detection_id.company_id.id,
            'picking_type_id': self.detection_id.picking_type_id.id,
            'origin': self.detection_id.name,
            'description_picking': 'Employee Detection Medicine Deliver',
            'warehouse_id': self.detection_id.picking_type_id.warehouse_id.id,
        }
        diff_quantity = self.product_qty
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
