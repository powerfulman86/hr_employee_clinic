# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.osv import expression
from odoo.tools.float_utils import float_compare
from odoo.exceptions import AccessError, UserError, ValidationError
from datetime import date, datetime
from odoo.tools.misc import format_date
from dateutil.relativedelta import relativedelta

AVAILABLE_STATE = [
    ('draft', 'Draft'),
    ('approve', 'Approved'),
    ('start', 'Start'),
    ('close', 'Close'),
]


class HrEmployeeMedication(models.Model):
    _name = 'hr.employee.medication'
    _rec_name = 'name'
    _description = 'Employee Medication'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']

    name = fields.Char('Name')
    company_id = fields.Many2one('res.company', 'Company', required=True, index=True,
                                 default=lambda self: self.env.company.id)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.uid, index=True,
                              tracking=True)
    branch_id = fields.Many2one(comodel_name="res.branch", string="Branch", required=True,
                                index=True, help='This is branch to set')
    employee_id = fields.Many2one('hr.employee', string='Employee', auto_join=True, tracking=True, required=True)
    department_id = fields.Many2one('hr.department', related='employee_id.department_id',
                                    string='Employee Department', readonly=True, store=True)
    state = fields.Selection(AVAILABLE_STATE, string='State', index=True, default=AVAILABLE_STATE[0][0],
                             tracking=True, )
    start_date = fields.Datetime(string='Start Date', default=fields.Datetime.now, readonly=True, )
    approve_date = fields.Datetime(string='Approve Date', default=fields.Datetime.now, readonly=True, )
    close_date = fields.Datetime(string='Close Date', default=fields.Datetime.now, readonly=True, )
    notes = fields.Html('Notes', help='Notes')
    doctor_id = fields.Many2one('res.partner', string='Doctor', domain="[('is_doctor', '=', True)]",
                                auto_join=True, tracking=True, required=True)
    medication_line = fields.One2many('hr.employee.medication.line', 'medication_id', string='Medication Line',
                                      copy=True, auto_join=True, readonly=True, states={'draft': [('readonly', False)]})

    @api.model
    def create(self, values):
        res = super(HrEmployeeMedication, self).create(values)
        res.name = self.env['ir.sequence'].next_by_code('clinic.detection') or '/'
        return res

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('name', operator, name), ('employee_id', operator, name)]
        medication_ids = self._search(expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid)
        return models.lazy_name_get(self.browse(medication_ids).with_user(name_get_uid))

    @api.depends('name', 'employee_id')
    def name_get(self):
        result = []
        for rec in self:
            name = rec.name
            if rec.employee_id:
                name += ' (' + rec.employee_id.name + ')'
            result.append((rec.id, name))
        return result

    def unlink(self):
        for rec in self:
            if not rec.state == 'draft':
                raise UserError(_("Employee Medication Can't Be Deleted After draft, you can close it instead ."))
        return super(HrEmployeeMedication, self).unlink()

    def action_approve(self):
        self.write({'state': "approve"})

    def action_start(self):
        self.write({'state': "start"})

    def action_close(self):
        self.write({'state': "close"})


class HrEmployeeMedicationLine(models.Model):
    _name = 'hr.employee.medication.line'
    _rec_name = 'name'
    _description = 'Employee Medication'

    name = fields.Text(string='Description', )
    medication_id = fields.Many2one('hr.employee.medication', string='Medication Reference', required=True,
                                    ondelete='cascade', index=True, copy=False)
    employee_id = fields.Many2one(related='medication_id.employee_id', string='Employee', auto_join=True,)
    department_id = fields.Many2one(related='medication_id.department_id',
                                    string='Employee Department', readonly=True, store=True)
    branch_id = fields.Many2one(related='medication_id.branch_id', string="Branch", index=True)
    start_date = fields.Datetime(related='medication_id.start_date', string='Start Date', readonly=True)
    company_id = fields.Many2one('res.company', related='medication_id.company_id', string='Company', store=True,
                                 readonly=True)
    sequence = fields.Integer(string='Sequence', default=10)
    product_id = fields.Many2one('product.product', string='Product', domain="[('is_medicine', '=', True)]",
                                 change_default=True, ondelete='restrict', check_company=True)  # Unrequired company
    product_template_id = fields.Many2one('product.template', string='Product Template',
                                          related="product_id.product_tmpl_id", domain=[('is_medicine', '=', True)])

    product_qty = fields.Float(string='Quantity', digits='Product Quantity', required=True, default=1.0)
    product_uom_qty = fields.Float(string='Uom Quantity', digits='Product Unit of Measure', required=True, default=1.0)
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure',
                                  domain="[('category_id', '=', product_uom_category_id)]")
    product_uom_category_id = fields.Many2one(related='product_id.uom_id.category_id', readonly=True)

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


class ClinicMedication(models.Model):
    _name = 'clinic.medication'
    _rec_name = 'name'
    _description = 'Clinic Medication'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']

    name = fields.Char()
    state = fields.Selection([
        ('draft', 'Draft'),
        ('verify', 'Verify'),
        ('close', 'Done'),
    ], string='Status', index=True, readonly=True, copy=False, default='draft')
    medication_batch_id = fields.Many2one('clinic.medication.batch', string='Batch Name', readonly=True,
                                          copy=False,
                                          states={'draft': [('readonly', False)], 'verify': [('readonly', False)]},
                                          ondelete='cascade',
                                          domain="[('company_id', '=', company_id)]")
    company_id = fields.Many2one('res.company', string='Company', readonly=True, required=True,
                                 default=lambda self: self.env.company)
    branch_id = fields.Many2one(comodel_name="res.branch", string="Branch", required=True,
                                index=True, help='This is branch to set')
    employee_id = fields.Many2one('hr.employee', string='Employee', auto_join=True, tracking=True, required=True)
    department_id = fields.Many2one('hr.department', related='employee_id.department_id',
                                    string='Employee Department', readonly=True, store=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.uid, index=True,
                              tracking=True)
    date_from = fields.Date(string='From', readonly=True, required=True,
                            default=lambda self: fields.Date.to_string(date.today().replace(day=1)),
                            states={'draft': [('readonly', False)], 'verify': [('readonly', False)]})
    date_to = fields.Date(string='To', readonly=True, required=True,
                          default=lambda self: fields.Date.to_string(
                              (datetime.now() + relativedelta(months=+1, day=1, days=-1)).date()),
                          states={'draft': [('readonly', False)], 'verify': [('readonly', False)]})
    line_ids = fields.One2many('clinic.medication.line', 'medication_id', string='Medication Lines', readonly=True,
                               states={'draft': [('readonly', False)]})
    notes = fields.Html('Notes', help='Notes')

    def unlink(self):
        if any(self.filtered(lambda medication: medication.state not in ('draft', 'cancel'))):
            raise UserError(_('You cannot delete a Medication which is not draft or cancelled!'))
        return super(ClinicMedication, self).unlink()

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        if any(self.filtered(lambda payslip: payslip.date_from > payslip.date_to)):
            raise ValidationError(_("Medication 'Date From' must be earlier 'Date To'."))

    @api.onchange('employee_id', 'date_from', 'date_to')
    def _onchange_employee(self):
        self.name = '%s - %s - %s' % (
            'Employee Medication', self.employee_id.name or '',
            format_date(self.env, self.date_from, date_format="MMMM y"))


class ClinicMedicationLine(models.Model):
    _name = 'clinic.medication.line'
    _rec_name = 'name'
    _description = 'Clinic Medication Line'

    name = fields.Char()
    medication_id = fields.Many2one(comodel_name="clinic.medication", string="Medication Id", required=False, )
    employee_id = fields.Many2one(related='medication_id.employee_id', string='Employee', auto_join=True, )
    department_id = fields.Many2one(related='medication_id.department_id',
                                    string='Employee Department', readonly=True, store=True)
    branch_id = fields.Many2one(related='medication_id.branch_id', string="Branch", index=True)
    sequence = fields.Integer(string='Sequence', default=10)
    product_id = fields.Many2one('product.product', string='Product', domain="[('is_medicine', '=', True)]",
                                 change_default=True, ondelete='restrict', check_company=True)  # Unrequired company
    product_template_id = fields.Many2one('product.template', string='Product Template',
                                          related="product_id.product_tmpl_id", domain=[('is_medicine', '=', True)])

    product_qty = fields.Float(string='Quantity', digits='Product Quantity', required=True, default=1.0)
    product_uom_qty = fields.Float(string='Uom Quantity', digits='Product Unit of Measure', required=True, default=1.0)
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure',
                                  domain="[('category_id', '=', product_uom_category_id)]")
    product_uom_category_id = fields.Many2one(related='product_id.uom_id.category_id', readonly=True)

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


class ClinicMedicationBatch(models.Model):
    _name = 'clinic.medication.batch'
    _rec_name = 'name'
    _description = 'Clinic Medication Batch'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']

    name = fields.Char(required=True, readonly=True, states={'draft': [('readonly', False)]})
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.uid, index=True,
                              tracking=True)
    branch_id = fields.Many2one(comodel_name="res.branch", string="Branch", required=True,
                                index=True, help='This is branch to set')
    medication_ids = fields.One2many('clinic.medication', 'medication_batch_id', string='Medications', readonly=True,
                                     states={'draft': [('readonly', False)]})
    state = fields.Selection([
        ('draft', 'Draft'),
        ('verify', 'Verify'),
        ('close', 'Done'),
    ], string='Status', index=True, readonly=True, copy=False, default='draft')
    company_id = fields.Many2one('res.company', string='Company', readonly=True, required=True,
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='Department', )
    date_start = fields.Date(string='Date From', required=True, readonly=True,
                             states={'draft': [('readonly', False)]},
                             default=lambda self: fields.Date.to_string(date.today().replace(day=1)))
    date_end = fields.Date(string='Date To', required=True, readonly=True,
                           states={'draft': [('readonly', False)]},
                           default=lambda self: fields.Date.to_string(
                               (datetime.now() + relativedelta(months=+1, day=1, days=-1)).date()))
    medication_count = fields.Integer(compute='_compute_medication_count')
    notes = fields.Html('Notes', help='Notes')

    def _compute_medication_count(self):
        for rec in self:
            rec.medication_count = len(self.medication_ids)

    def action_draft(self):
        return self.write({'state': 'draft'})

    def action_close(self):
        if self._are_medication_ready():
            self.write({'state': 'close'})

    def _are_medication_ready(self):
        return all(medic.state in ['done', 'cancel'] for medic in self.mapped('medication_ids'))

    @api.onchange('department_id', 'date_start', 'date_end')
    def _onchange_department(self):

        self.name = '%s - %s - %s' % (
            'Medication Batch', self.department_id.name or '',
            format_date(self.env, self.date_start, date_format="MMMM y"))

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        if any(self.filtered(lambda payslip: payslip.date_start > payslip.date_end)):
            raise ValidationError(_("Medication Batch 'Date Start' must be earlier 'Date End'."))

    def unlink(self):
        if any(self.filtered(lambda batch: batch.state not in ('draft', 'cancel'))):
            raise UserError(_('You cannot delete a Batch which is not draft or cancelled!'))
        return super(ClinicMedicationBatch, self).unlink()
