#-*- coding:utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015 One Click Software (http://oneclick.solutions)
#    and Copyright (C) 2013 Michael Telahun Makonnen <mmakonnen@gmail.com>.
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

from openerp.osv import fields, osv
from openerp.tools.translate import _

class schedule_ot(osv.TransientModel):

    _name ='hr.schedule.ot.employees'
    _description = 'Generate scheduled OT for selected employees'
    
    _columns = {
        'employee_ids': fields.many2many('hr.employee', 'hr_employee_schedule_ot_rel', 'schedule_ot_id', 'employee_id', 'Employees'),
    }
    
    def create_ot(self, cr, uid, ids, context=None):
        
        emp_pool = self.pool.get('hr.employee')
        schedot_pool = self.pool.get('hr.schedule.ot')
        batch_pool = self.pool.get('hr.schedule.ot.batch')
        
        if context is None:
            context = {}
        
        data = self.read(cr, uid, ids, context=context)[0]
        if not data['employee_ids']:
            raise osv.except_osv(_("Warning !"), _("You must select at least one employee."))
        
        batch_id = context.get('active_id', False)
        if not batch_id:
            raise osv.except_osv(_('Internal Error'), _('Unable to determine ID of batch scheduled OT'))
        
        batch_data = batch_pool.read(cr, uid, batch_id, ['week_start'], context=context)
        
        for emp in emp_pool.browse(cr, uid, data['employee_ids'], context=context):
            
            res = {
                'week_start': batch_data.get('week_start', False),
                'employee_id': emp.id,
                'batch_id': batch_id,
            }
            schedot_pool.create(cr, uid, res, context=context)
        
        return {'type': 'ir.actions.act_window_close'}
