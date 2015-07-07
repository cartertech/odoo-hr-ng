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

from pytz import common_timezones

from openerp.addons.decimal_precision import decimal_precision as dp
from openerp.osv import fields, osv

class policy_presence(osv.Model):
    
    _name = 'hr.policy.presence'
    
    _columns = {
        'name': fields.char('Name', size=128, required=True),
        'date': fields.date('Effective Date', required=True),
        'work_hours_per_week': fields.integer('Working Hours/Week', required=True),
        'line_ids': fields.one2many('hr.policy.line.presence', 'policy_id', 'Policy Lines'),
    }
    
    _defaults = {
        'work_hours_per_week': 40,
    }
    
    # Return records with latest date first
    _order = 'date desc'
    
    def get_codes(self, cr, uid, idx, context=None):
        
        res = []
        [res.append((line.code, line.name, line.type, line.rate, line.duration, line.accrual_policy_line_id.id,
                     line.accrual_policy_line_id.code, line.accrual_rate, line.accrual_min, line.accrual_max)) for line in self.browse(cr, uid, idx, context=context).line_ids]
        return res

class policy_line_presence(osv.Model):
    
    _name = 'hr.policy.line.presence'
    
    _columns = {
        'name': fields.char('Name', size=64, required=True),
        'policy_id': fields.many2one('hr.policy.presence', 'Policy'),
        'code': fields.char('Code', required=True, help="Use this code in the salary rules."),
        'rate': fields.float('Rate', required=True, help='Multiplier of employee wage.'),
        'type': fields.selection([('normal', 'Normal Working Hours'),
                                  ('holiday', 'Holidays'),
                                  ('restday', 'Rest Days')],
                                 'Type', required=True),
        'active_after': fields.integer('Active After', required=True, help='Minutes after first punch of the day in which policy will take effect.'),
        'duration': fields.integer('Duration', required=True, help="In minutes."),
        'accrual_policy_line_id': fields.many2one('hr.policy.line.accrual', 'Accrual Policy Line'),
        'accrual_rate': fields.float('Accrual Rate', digits_compute=dp.get_precision('Accruals')),
        'accrual_min': fields.float('Minimum Accrual', digits_compute=dp.get_precision('Accruals')),
        'accrual_max': fields.float('Maximum Accrual', digits_compute=dp.get_precision('Accruals')),
    }
    
    _defaults = {
        'rate': 1.0,
    }

class policy_group(osv.Model):
    
    _name = 'hr.policy.group'
    _inherit = 'hr.policy.group'
    
    _columns = {
        'presence_policy_ids': fields.many2many('hr.policy.presence', 'hr_policy_group_presence_rel',
                                          'group_id', 'presence_id', 'Presence Policy'),
    }
