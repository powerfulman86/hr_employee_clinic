# -*- coding: utf-8 -*-
# from odoo import http


# class HrEmployeeClinic(http.Controller):
#     @http.route('/hr_employee_clinic/hr_employee_clinic/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/hr_employee_clinic/hr_employee_clinic/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('hr_employee_clinic.listing', {
#             'root': '/hr_employee_clinic/hr_employee_clinic',
#             'objects': http.request.env['hr_employee_clinic.hr_employee_clinic'].search([]),
#         })

#     @http.route('/hr_employee_clinic/hr_employee_clinic/objects/<model("hr_employee_clinic.hr_employee_clinic"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('hr_employee_clinic.object', {
#             'object': obj
#         })
