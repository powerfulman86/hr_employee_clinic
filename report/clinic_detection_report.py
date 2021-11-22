# -*- coding: utf-8 -*-

from odoo import tools
from odoo import api, fields, models


class ClinicDetectionReport(models.Model):
    _name = 'clinic.detection.report'
    _description = "Clinic Detection Report"
    _auto = False

    name = fields.Char('Name')
    reference = fields.Char(string="Reference", required=False, )
    user_id = fields.Many2one('res.users', )
    branch_id = fields.Many2one("res.branch")
    detection_date = fields.Datetime('Detection Date')
    detection_notes = fields.Html('Notes', )
    detection_doctor = fields.Many2one('res.partner', )
    detection_employee = fields.Many2one('hr.employee', )
    department_id = fields.Many2one('hr.department', )
    product_id = fields.Many2one('product.product', )
    product_qty = fields.Float('Quantity', )
    product_uom = fields.Many2one('uom.uom', )

    def _query(self, with_clause='', fields={}, groupby='', from_clause=''):
        with_ = ("WITH %s" % with_clause) if with_clause else ""

        select_ = """
                    min(m.id) as id,
                    h.name	as name,
                    h.detection_date as detection_date,
                    h.user_id as user_id,
                    h.branch_id as branch_id,
                    h.detection_doctor as detection_doctor,
                    h.detection_employee as detection_employee,
                    h.department_id as department_id,
                    m.product_id as product_id,
                    t.uom_id as product_uom,
                    sum(m.product_qty) as product_qty
                """
        for field in fields.values():
            select_ += field

        from_ = """
                clinic_detection_medicine m
                join clinic_detection h on (h.id = m.detection_id)
                left join product_product p on (m.product_id=p.id)
                left join product_template t on (p.product_tmpl_id=t.id)
                left join uom_uom u on (u.id=m.product_uom)
                join res_partner partner on h.detection_doctor = partner.id
                join res_branch branch on h.branch_id = branch.id
                join hr_employee employee on h.detection_employee = employee.id 
                join hr_department department on h.department_id = department.id
                %s
        """ % from_clause

        groupby_ = """
            h.name,
            h.detection_date,
            h.user_id,
            h.branch_id,
            h.detection_doctor,
            h.detection_employee,
            h.department_id,
            m.product_id,
            t.uom_id %s
        """ % groupby

        return '%s (SELECT %s FROM %s WHERE m.product_id IS NOT NULL GROUP BY %s )' % (with_, select_, from_, groupby_)

    def init(self):
        # self._table = sale_report
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""CREATE or REPLACE VIEW %s as (%s)""" % (self._table, self._query()))
