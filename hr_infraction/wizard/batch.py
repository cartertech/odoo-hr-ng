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

import time

import openerp.netsvc
from openerp.osv import fields, orm, osv
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as OE_DFORMAT
from openerp.tools.translate import _

class infraction_batch(orm.TransientModel):

    _name ='hr.infraction.batch'
    _description = 'Generate mass infraction incidents'
    
    _columns = {
        'employee_ids': fields.many2many('hr.employee', 'hr_employee_infraction_batch_rel', 'infraction_id', 'employee_id', 'Employees'),
        'category_id': fields.many2one('hr.infraction.category', 'Infraction Category', required=True),
        'name': fields.char('Subject', size=256, required=True,),
        'date': fields.date('Date', required=True),
        'memo': fields.text('Description'),
    }
    
    _defaults = {
        'date': time.strftime(OE_DFORMAT),
    }
    
    def onchange_category(self, cr, uid, ids, category_id, context=None):
        
        res = {'value': {'name': False}}
        if category_id:
            category = self.pool.get('hr.infraction.category').browse(cr, uid, category_id,
                                                                      context=context)
            res['value']['name'] = category.name
        return res
    
    def create_infractions(self, cr, uid, ids, context=None):
        
        infra_obj = self.pool.get('hr.infraction')
        
        if context is None:
            context = {}
        
        data = self.read(cr, uid, ids, context=context)[0]
        if not data['employee_ids']:
            raise osv.except_osv(_("Warning !"), _("You must select at least one employee to generate wage adjustments."))
        
        infra_ids = []
        vals = {
            'name': data['name'],
            'category_id': data['category_id'][0],
            'date': data['date'],
            'memo': data['memo'],
            'employee_id': False,
        }
        for ee_id in data['employee_ids']:
            vals['employee_id'] = ee_id,
            infra_ids.append(infra_obj.create(cr, uid, vals, context=context))
        
        wkf_service = netsvc.LocalService('workflow')
        for i_id in infra_ids:
            wkf_service.trg_validate(uid, 'hr.infraction', i_id, 'signal_confirm', cr)
        
        return {'type': 'ir.actions.act_window_close'}
