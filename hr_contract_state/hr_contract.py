#-*- coding:utf-8 -*-
##############################################################################
#
#    Copyright (C) 2013-2015 Michael Telahun Makonnen <mmakonnen@gmail.com> and
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

from datetime import datetime
from dateutil.relativedelta import relativedelta

import openerp.netsvc
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT
from openerp.osv import fields, osv

class hr_contract(osv.osv):
    
    _name = 'hr.contract'
    _inherit = ['hr.contract', 'mail.thread', 'ir.needaction_mixin']
    
    def _get_ids_from_employee(self, cr, uid, ids, context=None):
        
        res = []
        for ee in self.pool.get('hr.employee').browse(cr, uid, ids, context=context):
            for contract in ee.contract_ids:
                if contract.state not in ['pending_done', 'done']:
                    res.append(contract.id)
        return res
    
    def _get_department(self, cr, uid, ids, field_name, arg, context=None):
        
        res = dict.fromkeys(ids, False)
        for contract in self.browse(cr, uid, ids, context=context):
            if contract.department_id and contract.state in ['pending_done', 'done']:
                res[contract.id] = contract.department_id.id
            elif contract.employee_id.department_id:
                res[contract.id] = contract.employee_id.department_id.id
        return res
    
    _columns = {
        'concurrent_contracts': fields.boolean('Concurrent Contracts', readonly=True),
        'date_end_effective': fields.date('Effective End Date', readonly=True),
        'date_end_original': fields.date('Original End Date', readonly=True),
        'state': fields.selection([('draft', 'Draft'),
                                   ('trial', 'Trial'),
                                   ('trial_ending', 'Trial Period Ending'),
                                   ('open', 'Open'),
                                   ('contract_ending', 'Ending'),
                                   ('pending_done', 'Pending Termination'),
                                   ('done', 'Completed')],
                                  'State',
                                  readonly=True),

        # store this field in the database and trigger a change only if the contract is
        # in the right state: we don't want future changes to an employee's department to
        # impact past contracts that have now ended. Increased priority to override hr_simplify.
        'department_id': fields.function(_get_department, type='many2one', method=True,
                                        obj='hr.department', string="Department", readonly=True,
                                        store={'hr.employee': (_get_ids_from_employee, ['department_id'], 10)}),
        
        # At contract end this field will hold the job_id, and the
        # job_id field will be set to null so that modules that 
        # reference job_id don't include deactivated employees.
        'end_job_id': fields.many2one('hr.job', 'Job Title', readonly=True),
        
        # The following are redefined again to make them editable only in certain states
        'employee_id': fields.many2one('hr.employee', "Employee", required=True, readonly=True,
                                       states={'draft': [('readonly', False)]}),
        'type_id': fields.many2one('hr.contract.type', "Contract Type", required=True, readonly=True,
                                   states={'draft': [('readonly', False)]}),
        'job_id': fields.many2one('hr.job', 'Job Title', required=False,
                                   states={
                                        'draft': [('required', True)],
                                        'trial': [('required', True)],
                                        'trial_ending': [('required', True)],
                                        'open': [('required', True)],
                                        'contract_ending': [('required', True)],
                                        'pending_done': [('required', True)],
                                    }),
        'date_start': fields.date('Start Date', required=True, readonly=True,
                                  states={'draft': [('readonly', False)]}),
        'wage': fields.float('Wage', digits=(16,2), required=True, readonly=True,
                             states={'draft': [('readonly', False)],
                                     'trial': [('readonly', False)],
                                     'trial_ending': [('readonly', False)]},
                             help="Basic Salary of the employee"),
    }
    
    _defaults = {
        'state': 'draft',
    }
    
    def _check_multiple_contracts(self, cr, uid, ids, context=None):
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        allow = True
        if len(ids) == 0:
            return allow
        
        for contract in self.browse(cr, uid, ids, context=context):
            allow = False
            if contract.concurrent_contracts:
                allow = True
                break
            else:
                c_ids = self.search(cr, uid, [('employee_id', '=', contract.employee_id.id),
                                              ('date_start', '<=', contract.date_end),
                                              '|', ('date_end', '=', False),
                                                   ('date_end', '>=', contract.date_start),
                                              ('id', '!=', contract.id)],
                                    context=context)
                if len(c_ids) > 0:
                    allow = False
                    break
                else:
                    allow = True
                    break
        
        return allow
    
    _constraints = [(_check_multiple_contracts, 'Multiple concurrent contracts not allowed!', ['date_start', 'date_end'])]
    
    _track = {
        'state': {
            'hr_contract_state.mt_alert_trial_ending': lambda self, cr,uid, obj, ctx=None: obj['state'] == 'trial_ending',
            'hr_contract_state.mt_alert_open': lambda self, cr,uid, obj, ctx=None: obj['state'] == 'open',
            'hr_contract_state.mt_alert_contract_ending': lambda self, cr,uid, obj, ctx=None: obj['state'] == 'contract_ending',
        },
    }
    
    def _needaction_domain_get(self, cr, uid, context=None):
        
        users_obj = self.pool.get('res.users')
        domain = []
        
        if users_obj.has_group(cr, uid, 'base.group_hr_manager'):
            domain = [('state', 'in', ['draft', 'contract_ending', 'trial_ending'])]
            return domain
        
        return False
    
    def onchange_job(self, cr, uid, ids, job_id, context=None):
        
        res = False
        if isinstance(ids, (int, long)):
            ids = [ids]
        if ids:
            contract = self.browse(cr, uid, ids[0], context=None)
            if contract.state != 'draft':
                return res
        return super(hr_contract, self).onchange_job(cr, uid, ids, job_id, context=context)
    
    def condition_trial_period(self, cr, uid, ids, context=None):
        
        dToday = datetime.now().date()
        for contract in self.browse(cr, uid, ids, context=context):
            if not contract.trial_date_start or \
              (contract.trial_date_end and contract.trial_date_end < dToday.strftime(DEFAULT_SERVER_DATE_FORMAT)):
                return False
        return True
    
    def try_signal_ending_contract(self, cr, uid, context=None):
        
        d = datetime.now().date() + relativedelta(days= +30)
        ids = self.search(cr, uid, [
                                    ('state', '=', 'open'),
                                    ('date_end', '<=', d.strftime(DEFAULT_SERVER_DATE_FORMAT))
                                   ], context=context)
        if len(ids) == 0: return
        
        wkf = netsvc.LocalService('workflow')
        [wkf.trg_validate(uid, 'hr.contract', contract.id, 'signal_ending_contract', cr) for contract in self.browse(cr, uid, ids, context=context)]
        
        return
    
    def try_signal_contract_completed(self, cr, uid, context=None):
        
        d = datetime.now().date()
        ids = self.search(cr, uid, [
                                    ('state', '=', 'open'),
                                    ('date_end', '<', d.strftime(DEFAULT_SERVER_DATE_FORMAT))
                                   ], context=context)
        if len(ids) == 0: return
        
        wkf = netsvc.LocalService('workflow')
        [wkf.trg_validate(uid, 'hr.contract', contract.id, 'signal_pending_done', cr) for contract in self.browse(cr, uid, ids, context=context)]
        
        return
    
    def try_signal_ending_trial(self, cr, uid, context=None):
        
        d = datetime.now().date() + relativedelta(days= +10)
        ids = self.search(cr, uid, [
                                    ('state', '=', 'trial'),
                                    ('trial_date_end', '<=', d.strftime(DEFAULT_SERVER_DATE_FORMAT))
                                   ], context=context)
        if len(ids) == 0: return
        
        wkf = netsvc.LocalService('workflow')
        [wkf.trg_validate(uid, 'hr.contract', contract.id, 'signal_ending_trial', cr) for contract in self.browse(cr, uid, ids, context=context)]
        
        return
    
    def try_signal_open(self, cr, uid, context=None):
        
        d = datetime.now().date() + relativedelta(days= -5)
        ids = self.search(cr, uid, [
                                    ('state', '=', 'trial_ending'),
                                    ('trial_date_end', '<=', d.strftime(DEFAULT_SERVER_DATE_FORMAT))
                                   ], context=context)
        if len(ids) == 0: return
        
        wkf = netsvc.LocalService('workflow')
        [wkf.trg_validate(uid, 'hr.contract', contract.id, 'signal_open', cr) for contract in self.browse(cr, uid, ids, context=context)]
        
        return
    
    def onchange_start(self, cr, uid, ids, date_start, context=None):
        
        res = { 'value': {} }
        res['value']['trial_date_start'] = date_start
        
        return res
    
    def state_trial(self, cr, uid, ids, context=None):
        
        self.write(cr, uid, ids, {'state': 'trial'}, context=context)
        return True
    
    def state_open(self, cr, uid, ids, context=None):
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        for i in ids:
            vals = {
                'state': 'open',
            }
            data = self.read(cr, uid, i, ['state', 'date_end_original'], context=context)
            if data['state'] == 'pending_done' and data.get('date_end_original', False):
                vals.update({'date_end': data['date_end_original'],
                             'date_end_originall': False})
            elif data['state'] == 'pending_done':
                vals.update({'date_end': False})
            
            self.write(cr, uid, i, vals, context=context)
        
        return True
    
    def state_pending_done(self, cr, uid, ids, context=None):
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        for i in ids:
            data = self.read(cr, uid, i, ['date_end', 'date_end_effective', 'date_end_original'],
                             context=context)
            vals = {'state': 'pending_done',
                    'date_end': False}
            if data.get('date_end', False):
                vals.update({'date_end_original': data['date_end']})
            
            if data.get('date_end_effective', False):
                vals['date_end'] = data['date_end_effective']
            else:
                vals['date_end'] = time.strftime(DEFAULT_SERVER_DATE_FORMAT)
                
            self.write(cr, uid, i, vals, context=context)
        
        return True
    
    def state_done(self, cr, uid, ids, context=None):
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        for i in ids:
            data = self.read(cr, uid, i, ['date_end', 'job_id'], context=context)
            vals = {'state': 'done',
                    'job_id': False,
                    'end_job_id': data['job_id'][0]}
            dToday = datetime.now().date()
            dEnd = dToday
            if data.get('date_end', False):
                dEnd = datetime.strptime(data['date_end'], DEFAULT_SERVER_DATE_FORMAT).date()
                if dEnd > dToday:
                    dEnd = dToday
                    vals.update({'date_end': dEnd.strftime(DEFAULT_SERVER_DATE_FORMAT)})
            else:
                    vals.update({'date_end': dEnd.strftime(DEFAULT_SERVER_DATE_FORMAT)})
            self.write(cr, uid, i, vals, context=context)
        
        return True

class hr_job(osv.osv):

    _name = 'hr.job'
    _inherit = 'hr.job'

    def _no_of_contracts(self, cr, uid, ids, name, args, context=None):
        res = {}
        for job in self.browse(cr, uid, ids, context=context):
            contract_ids = self.pool.get('hr.contract').search(cr, uid, [('job_id','=',job.id),
                                                                         ('state','!=','done')],
                                                               context=context)
            nb = len(contract_ids or [])
            res[job.id] = {
                'no_of_employee': nb,
                'expected_employees': nb + job.no_of_recruitment,
            }
        return res
