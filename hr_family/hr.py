#-*- coding:utf-8 -*-
##############################################################################
#
#    Copyright (C) 2011-2015 Michael Telahun Makonnen <mmakonnen@gmail.com> and
#    One Click Software <http://oneclick.solutions>.
#    All Rights Reserved.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from datetime import datetime

from openerp.osv import fields, osv
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as OE_DFORMAT

class hr_children(osv.osv):
    
    _name = 'hr.employee.children'
    _description = 'HR Employee Children'
    
    def _calculate_age(self, cr, uid, ids, field_name, arg, context=None):
        
        res = dict.fromkeys(ids, False)
        for ee in self.browse(cr, uid, ids, context=context):
            if ee.dob:
                dBday = datetime.strptime(ee.dob, OE_DFORMAT).date()
                dToday = datetime.now().date()
                res[ee.id] = (dToday - dBday).days / 365
        return res
    
    _columns = {
                'name': fields.char('Name', size=256, required=True),
                'dob': fields.date('Date of Birth'),
                'gender': fields.selection([('female', 'Female'), ('male', 'Male')],
                                           'Gender', required=False),
                'employee_id': fields.many2one('hr.employee', 'Employee'),
                'age': fields.function(_calculate_age, type='integer', method=True, string='Age'),
    }

class hr_employee(osv.osv):
    
    _name = 'hr.employee'
    _inherit = 'hr.employee'
    
    def _get_employee_ids_from_ee(self, cr, uid, ids, context=None):
        
        return ids
    
    def _get_employee_ids_from_children(self, cr, uid, ids, context=None):
        
        datas = self.pool.get('hr.employee.children').read(cr, uid, ids, ['employee_id'],
                                                           context=context)
        ee_ids = []
        for data in datas:
            if data.get('employee_id', False) and data['employee_id'][0] not in ee_ids:
                ee_ids.append(data['employee_id'][0])
        return ee_ids
    
    def _get_number_of_children(self, cr, uid, ids, field_name, arg, context=None):
        
        res = dict.fromkeys(ids, 0)
        for ee in self.browse(cr, uid, ids, context=context):
            for child in ee.fam_children_ids:
                res[ee.id] += 1
        return res
    
    _columns = {
                'fam_spouse': fields.char("Name", size=256),
                'fam_spouse_dob': fields.date("Date of Birth"),
                'fam_spouse_employer': fields.char("Employer", size=256),
                'fam_spouse_tel': fields.char("Telephone.", size=32),
                'fam_children_ids': fields.one2many('hr.employee.children', 'employee_id', 'Children'),
                'fam_father': fields.char("Father's Name", size=128),
                'fam_father_dob': fields.date('Date of Birth'),
                'fam_mother': fields.char("Mother's Name", size=128),
                'fam_mother_dob': fields.date('Date of Birth'),
                'fam_child_qty': fields.function(_get_number_of_children, type='integer', string="Number of Children",
                                                 store={
                                                        'hr.employee': (_get_employee_ids_from_ee, ['fam_children_ids'], 10),
                                                        'hr.employee.children': (_get_employee_ids_from_children, ['employee_id'], 10),
                                                       })
    }
