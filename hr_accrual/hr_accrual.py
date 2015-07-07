#-*- coding:utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014-2015 Michael Telahun Makonnen <mmakonnen@gmail.com> and
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

import time

import openerp.netsvc
from openerp.addons.decimal_precision import decimal_precision as dp
from openerp.osv import fields, osv
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as OE_DATEFORMAT
from openerp.tools.float_utils import float_compare

class hr_accrual(osv.Model):
    
    _name = 'hr.accrual'
    _description = 'Accrual'
    
    _columns = {
        'name': fields.char('Name', size=128, required=True),
        'holiday_status_id': fields.many2one('hr.holidays.status', 'Leave'),
        'line_ids': fields.one2many('hr.accrual.line', 'accrual_id', 'Accrual Lines', readonly=True),
    }
    
    def get_balance(self, cr, uid, ids, employee_id, date=None, context=None):
        
        if date == None:
            date = time.strftime(OE_DATEFORMAT)
        
        res = 0.0
        cr.execute('''SELECT SUM(amount) from hr_accrual_line \
                           WHERE accrual_id in %s AND employee_id=%s AND date <= %s''',
                           (tuple(ids), employee_id, date))
        for row in cr.fetchall():
            res = row[0]
        
        return res
    
    def deposit(self, cr, uid, ids, employee_id, amount, date_str, name=None, context=None):
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        line_obj = self.pool.get('hr.accrual.line')
        
        res = []
        for accrual in self.browse(cr, uid, ids, context=context):
            
            # Create accrual line
            #
            vals = {
                'date': date_str,
                'employee_id': employee_id,
                'amount': amount,
                'accrual_id': accrual.id,
            }
            res.append(line_obj.create(cr, uid, vals, context=context))
            
            if not accrual.holiday_status_id:
                break
            
            # Add the leave and trigger validation workflow
            # If the value is positive we do an allocation. If it's
            # negative we do a leave request, but set the date_from/date_to
            # to the same value.
            #
            leave_allocation = {
                'name': name != None and name or 'Allocation from Accrual',
                'type':  'add',
                'employee_id': employee_id,
                'number_of_days_temp': abs(amount),
                'holiday_status_id': accrual.holiday_status_id.id,
                'from_accrual': True,
            }
            if float_compare(amount, 0.0, precision_digits=1) == -1:
                leave_allocation['name'] = name != None and name or 'Removal from Accrual',
                leave_allocation['type'] = 'remove'
                leave_allocation.update({'date_from': date_str, 'date_to': date_str})
            
            holiday_id = self.pool.get('hr.holidays').create(cr, uid, leave_allocation, context=context)
            netsvc.LocalService('workflow').trg_validate(uid, 'hr.holidays', holiday_id, 'validate', cr)
            
        return res

class hr_accrual_line(osv.Model):
    
    _name = 'hr.accrual.line'
    _description = 'Accrual Line'
    
    _columns = {
        'date': fields.date('Date', required=True),
        'accrual_id': fields.many2one('hr.accrual', 'Accrual', required=True),
        'employee_id': fields.many2one('hr.employee', 'Employee', required=True),
        'amount': fields.float('Amount', required=True, digits_compute=dp.get_precision('Accruals')),
    }
    
    _defaults = {
        'date': time.strftime(OE_DATEFORMAT),
    }
    
    _rec_name = 'date'
