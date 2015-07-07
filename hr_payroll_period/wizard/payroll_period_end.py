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

import logging
from datetime import datetime
from dateutil.relativedelta import relativedelta

import openerp.netsvc
from openerp.addons.decimal_precision import decimal_precision as dp
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT as OEDATETIME_FORMAT
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as OEDATE_FORMAT
from openerp.tools.translate import _
from openerp.osv import fields, osv
from pytz import timezone, utc

_logger = logging.getLogger(__name__)

class payroll_period_end_1(osv.osv_memory):
    
    _name = 'hr.payroll.period.end.1'
    _description = 'End of Payroll Period Wizard Step 1'
    
    _exact_change = 0.00
    
    def _get_denominations(self, cr, uid, context=None):
        
        res = []
        self._exact_change = 0.00
        period_id = self._get_period_id(cr, uid, context=context)
        if not period_id:
            return res
        
        data = self.pool.get('hr.payroll.period').read(cr, uid, period_id, ['register_id'],
                                                       context=context)
        if not data.get('register_id', False):
            return res
        
        reg_obj = self.pool.get('hr.payroll.register')
        reg_obj.set_denominations(cr, uid, data['register_id'][0], context=context)
        data = reg_obj.read(cr, uid, data['register_id'][0], ['denomination_ids'], context=context)
        if data.get('denomination_ids', False):
            den_obj = self.pool.get('hr.payroll.register.denominations')
            for denomination in den_obj.browse(cr, uid, data['denomination_ids'], context=context):
                if len(res) == 0:
                    res.append((denomination.id, denomination.denomination))
                    continue
                
                idx = 0
                last_idx = len(res) - 1
                for i,v in res:
                    if denomination.denomination > v:
                        res.insert(idx, (denomination.id, denomination.denomination))
                        break
                    elif idx == last_idx:
                        res.append((denomination.id, denomination.denomination))
                        break
                    idx += 1
            res = [i for i,v in res]
            for den in self.pool.get('hr.payroll.register.denominations').browse(cr, uid, res,
                                                                                 context=context):
                self._exact_change += (den.denomination * den.denomination_qty)
        
        return res
    
    def _get_exact_change(self, cr, uid, context=None):
        
        return self._exact_change
    
    _columns = {
        'period_id': fields.integer('Period ID'),
        'is_ended': fields.boolean('Past End Day?'),
        'public_holiday_ids': fields.many2many('hr.holidays.public.line', 'hr_holidays_pay_period_rel', 'holiday_id', 'period_id', 'Public Holidays', readonly=True),
        'alert_critical': fields.integer('Critical Severity', readonly=True),
        'alert_high': fields.integer('High Severity', readonly=True),
        'alert_medium': fields.integer('Medium Severity', readonly=True),
        'alert_low': fields.integer('Low Severity', readonly=True),
        'pex_critical': fields.integer('Critical', readonly=True),
        'pex_high': fields.integer('High', readonly=True),
        'pex_medium': fields.integer('Medium', readonly=True),
        'pex_low': fields.integer('Low', readonly=True),
        'locked': fields.boolean('Is Period Locked?', readonly=True),
        'can_unlock': fields.boolean('Can Unlock Period?', readonly=True),
        'payslips': fields.boolean('Have Pay Slips Been Generated?', readonly=True),
        'ps_generated': fields.boolean('Pay Slip Generated?', readonly=True),
        'payment_started': fields.boolean('Payment Started?', readonly=True),
        'denomination_ids': fields.many2many('hr.payroll.register.denominations', 'pay_period_end_denomination_rel',
                                             'denomination_id', 'wizard_id',
                                             'Denomination Quantities', readonly=True),
        'exact_change': fields.float('Exact Change Total', digits_compute=dp.get_precision('Account')),
        'closed': fields.boolean('Pay Period Closed?', readonly=True),
        'ps_amendments_conf': fields.many2many('hr.payslip.amendment', 'hr_payslip_pay_period_rel', 'amendment_id', 'period_id', 'Confirmed Amendments', readonly=True),
        'ps_amendments_draft': fields.many2many('hr.payslip.amendment', 'hr_payslip_pay_period_rel', 'amendment_id', 'period_id', 'Draft Amendments', readonly=True),        
    }
    
    def _get_period_id(self, cr, uid, context=None):
        
        if context == None: context = {}
        return context.get('active_id', False)
    
    def _get_is_ended(self, cr, uid, context=None):
        
        flag = False
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if period_id:
            flag = self.pool.get('hr.payroll.period').is_ended(cr, uid, period_id, context=context)
        return flag
    
    def _alerts_count(self, cr, uid, severity, context=None):
        
        alert_obj = self.pool.get('hr.schedule.alert')
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        
        alert_ids = []
        if period_id:
            period = self.pool.get('hr.payroll.period').browse(cr, uid, period_id, context=context)
            if period:
                employee_ids = []
                [employee_ids.append(c.employee_id.id) for c in period.schedule_id.contract_ids]
                alert_ids = alert_obj.search(cr, uid, ['&', ('name', '>=', period.date_start),
                                                            ('name', '<=', period.date_end),
                                                       ('severity', '=', severity),
                                                       ('employee_id', 'in', employee_ids),
                                                      ],
                                             context=context)
        return len(alert_ids)
    
    def _critical_alerts(self, cr, uid, context=None):
        
        return self._alerts_count(cr, uid, 'critical', context)
    
    def _high_alerts(self, cr, uid, context=None):
        
        return self._alerts_count(cr, uid, 'high', context)
    
    def _medium_alerts(self, cr, uid, context=None):
        
        return self._alerts_count(cr, uid, 'medium', context)
    
    def _low_alerts(self, cr, uid, context=None):
        
        return self._alerts_count(cr, uid, 'low', context)
    
    def _pex_count(self, cr, uid, severity, context=None):
        
        ex_obj = self.pool.get('hr.payslip.exception')
        run_obj = self.pool.get('hr.payslip.run')
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        
        ex_ids = []
        slip_ids = []
        if period_id:
            period = self.pool.get('hr.payroll.period').browse(cr, uid, period_id, context=context)
            if period and period.register_id:
                for run_id in period.register_id.run_ids:
                    data = run_obj.read(cr, uid, run_id.id, ['slip_ids'], context=context)
                    [slip_ids.append(i) for i in data['slip_ids']]
                ex_ids = ex_obj.search(cr, uid, [('severity', '=', severity),
                                                 ('slip_id', 'in', slip_ids),
                                                ],
                                       context=context)
        return len(ex_ids)
    
    def _pex_critical(self, cr, uid, context=None):
        
        return self._pex_count(cr, uid, 'critical', context)
    
    def _pex_high(self, cr, uid, context=None):
        
        return self._pex_count(cr, uid, 'high', context)
    
    def _pex_medium(self, cr, uid, context=None):
        
        return self._pex_count(cr, uid, 'medium', context)
    
    def _pex_low(self, cr, uid, context=None):
        
        return self._pex_count(cr, uid, 'low', context)
    
    def _no_missing_punches(self, cr, uid, context=None):
        
        ids = self._missing_punches(cr, uid, context)
        res = len(ids)
        return res
    
    def _missing_punches(self, cr, uid, context=None):
        
        #
        # XXX - Someone who cares about DST should update this code to handle it.
        #
        
        missing_punch_ids = []
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if period_id:
            period = self.pool.get('hr.payroll.period').browse(cr, uid, period_id, context=context)
            if period:
                attendance_obj = self.pool.get('hr.attendance')
                utc_tz = timezone('UTC')
                dt = datetime.strptime(period.date_start, '%Y-%m-%d %H:%M:%S')
                utcDtStart = utc_tz.localize(dt, is_dst=False)
                dt = datetime.strptime(period.date_end, '%Y-%m-%d %H:%M:%S')
                utcDtEnd = utc_tz.localize(dt, is_dst=False)
                for contract in period.schedule_id.contract_ids:
                    employee = contract.employee_id
                    punch_ids = attendance_obj.search(cr, uid, [
                                                                ('employee_id','=',employee.id),
                                                                '&', ('name','>=', utcDtStart.strftime('%Y-%m-%d %H:%M:S')),
                                                                     ('name','<=', utcDtEnd.strftime('%Y-%m-%d %H:%M:S')),
                                                               ], order='name', context=context)
                    prevPunch = False
                    punches = None
                    if len(punch_ids) > 0:
                        punches = attendance_obj.browse(cr, uid, punch_ids, context=context)
                        for punch in punches:
                            if not prevPunch:
                                # First Punch must be a sign-in
                                if punch.action != 'sign_in':
                                    missing_punch_ids.append(punch.id)
                            elif punch.action == 'sign_in':
                                if prevPunch.action != 'sign_out':
                                    missing_punch_ids.append(prevPunch.id)
                            elif punch.action == 'sign_out':
                                if prevPunch.action != 'sign_in':
                                    missing_punch_ids.append(punch.id)
                            prevPunch = punch
                        # The last punch should be a sign out
                        if prevPunch and prevPunch.action != 'sign_out':
                            missing_punch_ids.append(prevPunch.id)
        return missing_punch_ids
    
    def _get_locked(self, cr, uid, context=None):
        
        flag = False
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if period_id:
            data = self.pool.get('hr.payroll.period').read(cr, uid, period_id, ['state'], context=context)
            flag = (data.get('state') in ['locked', 'generate', 'payment', 'closed'])
        
        return flag
    
    def _get_can_unlock(self, cr, uid, context=None):
        
        flag = False
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if period_id:
            data = self.pool.get('hr.payroll.period').read(cr, uid, period_id, ['state'], context=context)
            flag = (data.get('state') in ['locked', 'generate'])
        
        return flag
    
    def _get_payslips(self, cr, uid, context=None):
        
        flag = False
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if period_id:
            data = self.pool.get('hr.payroll.period').read(cr, uid, period_id, ['state', 'register_id'], context=context)
            if data.get('state') in ['generate', 'payment', 'closed'] and data.get('register_id', False):
                flag = True
        
        return flag
    
    def _get_ps_generated(self, cr, uid, context=None):
        
        flag = False
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if period_id:
            data = self.pool.get('hr.payroll.period').read(cr, uid, period_id, ['state'], context=context)
            if data.get('state') in ['generate']:
                flag = True
        
        return flag
    
    def _get_payment_started(self, cr, uid, context=None):
        
        flag = False
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if period_id:
            data = self.pool.get('hr.payroll.period').read(cr, uid, period_id, ['state'], context=context)
            if data.get('state') in ['payment', 'closed']:
                flag = True
        
        return flag
    
    def _get_closed(self, cr, uid, context=None):
        
        flag = False
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if period_id:
            data = self.pool.get('hr.payroll.period').read(cr, uid, period_id, ['state'], context=context)
            if data.get('state') in ['closed']:
                flag = True
        
        return flag
    
    def _get_public_holidays(self, cr, uid, context=None):
        
        holiday_ids = []
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id: return holiday_ids
        
        # XXX - Someone interested in DST should fix this.
        #
        period = self.pool.get('hr.payroll.period').browse(cr, uid, period_id, context=context)
        local_tz = timezone(period.schedule_id.tz)
        utcdtStart = utc.localize(datetime.strptime(period.date_start, OEDATETIME_FORMAT), is_dst=False)
        dtStart = utcdtStart.astimezone(local_tz)
        utcdtEnd = utc.localize(datetime.strptime(period.date_end, OEDATETIME_FORMAT), is_dst=False)
        dtEnd = utcdtEnd.astimezone(local_tz)
        start = dtStart.strftime(OEDATE_FORMAT)
        end = dtEnd.strftime(OEDATE_FORMAT)
        holiday_ids = self.pool.get('hr.holidays.public.line').search(cr, uid, [
                                                                                '&',
                                                                                    ('date', '>=', start),
                                                                                    ('date', '<=', end),
                                                                               ], context=context)
        
        return holiday_ids
    
    def _get_confirmed_amendments(self, cr, uid, context=None):
        
        psa_ids = []
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id: return psa_ids
        
        psa_ids = self.pool.get('hr.payslip.amendment').search(cr, uid, [('pay_period_id', '=', period_id),
                                                                         ('state', 'in', ['validate']),
                                                                        ],
                                                               context=context)
        return psa_ids
    
    def _get_draft_amendments(self, cr, uid, context=None):
        
        psa_ids = []
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id: return psa_ids
        
        psa_ids = self.pool.get('hr.payslip.amendment').search(cr, uid, [('pay_period_id', '=', period_id),
                                                                         ('state', 'in', ['draft']),
                                                                        ],
                                                               context=context)
        return psa_ids
    
    _defaults = {
        'period_id': _get_period_id,
        'is_ended': _get_is_ended,
        'public_holiday_ids': _get_public_holidays,
        'alert_critical': _critical_alerts,
        'alert_high': _high_alerts,
        'alert_medium': _medium_alerts,
        'alert_low': _low_alerts,
        'pex_critical': _pex_critical,
        'pex_high': _pex_high,
        'pex_medium': _pex_medium,
        'pex_low': _pex_low,
        'locked': _get_locked,
        'can_unlock': _get_can_unlock,
        'ps_generated': _get_ps_generated,
        'payslips': _get_payslips,
        'payment_started': _get_payment_started,
        'closed': _get_closed,
        'ps_amendments_conf': _get_confirmed_amendments,
        'ps_amendments_draft': _get_draft_amendments,
        'denomination_ids': _get_denominations,
        'exact_change': _get_exact_change,
    }
    
    def reload(self, cr, uid, ids, context=None):
        
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.payroll.period.end.1',
            'type': 'ir.actions.act_window',
            'target': 'current',
            'context': context
        }
    
    def view_alerts(self, cr, uid, ids, context=None):
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        
        employee_ids = []
        if period_id:
            period = self.pool.get('hr.payroll.period').browse(cr, uid, period_id, context=context)
            if period:
                [employee_ids.append(c.employee_id.id) for c in period.schedule_id.contract_ids]
        
        return {
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'hr.schedule.alert',
            'domain': [('employee_id', 'in', employee_ids), '&', ('name', '>=', period.date_start), ('name', '<=', period.date_end)],
            'type': 'ir.actions.act_window',
            'target': 'current',
            'context': context
        }
    
    def view_payroll_exceptions(self, cr, uid, ids, context=None):
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        
        ex_obj = self.pool.get('hr.payslip.exception')
        run_obj = self.pool.get('hr.payslip.run')
        
        ex_ids = []
        slip_ids = []
        if period_id:
            period = self.pool.get('hr.payroll.period').browse(cr, uid, period_id, context=context)
            if period:
                for run_id in period.register_id.run_ids:
                    data = run_obj.read(cr, uid, run_id.id, ['slip_ids'], context=context)
                    [slip_ids.append(i) for i in data['slip_ids']]
                ex_ids = ex_obj.search(cr, uid, [('slip_id', 'in', slip_ids)], context=context)
        
        return {
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'hr.payslip.exception',
            'domain': [('id', 'in', ex_ids)],
            'type': 'ir.actions.act_window',
            'target': 'current',
            'context': context
        }
    
    def _do_recalc_alerts(self, cr, uid, ids, context=None):
        
        alert_obj = self.pool.get('hr.schedule.alert')
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        
        if period_id:
            period = self.pool.get('hr.payroll.period').browse(cr, uid, period_id, context=context)
            if period:
                employee_ids = []
                [employee_ids.append(c.employee_id.id) for c in period.schedule_id.contract_ids]
                
                dtStart = datetime.strptime(period.date_start, '%Y-%m-%d %H:%M:%S')
                dtEnd = datetime.strptime(period.date_end, '%Y-%m-%d %H:%M:%S')
                
                dtNext = dtStart
                while dtNext <= dtEnd:
                    for employee_id in employee_ids:
                        alert_obj.compute_alerts_by_employee(cr, uid, employee_id,
                                                             dtNext.date().strftime('%Y-%m-%d'),
                                                             context=context)
                    dtNext += relativedelta(days= +1)
    
    def recalc_alerts(self, cr, uid, ids, context=None):
        
        self._do_recalc_alerts(cr, uid, ids, context=context)
        
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.payroll.period.end.1',
            'type': 'ir.actions.act_window',
            'target': 'inline',
            'context': context
        }
    
    def lock_period(self, cr, uid, ids, context=None):
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id: return
        
        # XXX - should not be necessary any more
        # Make sure to re-calculate alerts first. Just in case.
        #self._do_recalc_alerts(cr, uid, ids, context=context)
        
        data = self.read(cr, uid, ids[0], ['alert_critical'], context=context)
        if data.get('alert_critical') != 0:
            raise osv.except_osv(_('Unable to Lock the Payroll Period'), _('There are one or more Critical Severity Exceptions. Please correct them before proceeding.'))
        
        wkf_service = netsvc.LocalService('workflow')
        wkf_service.trg_validate(uid, 'hr.payroll.period', period_id, 'lock_period', cr)
        
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.payroll.period.end.1',
            'type': 'ir.actions.act_window',
            'target': 'inline',
            'context': context
        }
    
    def _remove_register(self, cr, uid, register_id, context=None):
        
        reg_obj = self.pool.get('hr.payroll.register')
        run_obj = self.pool.get('hr.payslip.run')
        slip_obj = self.pool.get('hr.payslip')
        reg_data = reg_obj.read(cr, uid, register_id, ['run_ids'], context=context)
        for run_id in reg_data['run_ids']:
            run_data = run_obj.read(cr, uid, run_id, ['slip_ids'], context=context)
            slip_obj.unlink(cr, uid, run_data['slip_ids'], context=context)
        run_obj.unlink(cr, uid, reg_data['run_ids'], context=context)
        reg_obj.unlink(cr, uid, register_id, context=context)
    
    def unlock_period(self, cr, uid, ids, context=None):
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id: return
        
        # Re-wind pay period if we are in payslip generation state
        #
        p_data = self.pool.get('hr.payroll.period').read(cr, uid, period_id,
                                                         ['state', 'register_id'],
                                                         context=context)
        if p_data['state'] == 'generate':
            self._remove_register(cr, uid, p_data['register_id'][0], context=context)
        
        wkf_service = netsvc.LocalService('workflow')
        wkf_service.trg_validate(uid, 'hr.payroll.period', period_id, 'unlock_period', cr)
        
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.payroll.period.end.1',
            'type': 'ir.actions.act_window',
            'target': 'inline',
            'context': context
        }
    
    def create_payroll_register(self, cr, uid, ids, context=None):
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id: return
        
        # Get relevant data from the period object
        period_obj = self.pool.get('hr.payroll.period')
        p_data = period_obj.read(cr, uid, period_id,
                                 ['name', 'date_start', 'date_end', 'schedule_id', 'register_id', 'state'],
                                 context=context)
        
        if p_data['state'] not in ['locked', 'generate']:
            raise osv.except_osv(_('Invalid Action'), _('You must lock the payroll period first.'))
        
        # Remove any pre-existing payroll registers
        if p_data['register_id']:
            self._remove_register(cr, uid, p_data['register_id'][0], context)
        
        # Create the payroll register
        register_obj = self.pool.get('hr.payroll.register')
        register_id = register_obj.create(cr, uid, {
                                                    'name': p_data['name'] + ': Register',
                                                    'date_start': p_data['date_start'],
                                                    'date_end': p_data['date_end'],
                                                   }, context=context)
        
        # Get list of departments and list of contracts for this period's schedule
        r_data = register_obj.read(cr, uid, register_id, ['company_id'], context=context)
        
        department_ids = self.pool.get('hr.department').search(cr, uid,
                                                               [('company_id', '=', r_data['company_id'][0])],
                                                               context=context)
        s_data = self.pool.get('hr.payroll.period.schedule').read(cr, uid, p_data['schedule_id'][0],
                                                                  ['annual_pay_periods', 'contract_ids', 'tz'], context=context)
        
        # DateTime in db is stored as naive UTC. Convert it to explicit UTC and then convert
        # that into the time zone of the pay period schedule.
        #
        local_tz = timezone(s_data['tz'])
        utcDTStart = utc.localize(datetime.strptime(p_data['date_start'], OEDATETIME_FORMAT))
        loclDTStart = utcDTStart.astimezone(local_tz)
        utcDTEnd = utc.localize(datetime.strptime(p_data['date_end'], OEDATETIME_FORMAT))
        loclDTEnd = utcDTEnd.astimezone(local_tz)
        
        # Create payslips for employees, in all departments, that have a contract in this
        # pay period's schedule
        self.create_payslip_runs(cr, uid, register_id, department_ids, s_data['contract_ids'],
                                 loclDTStart.date(), loclDTEnd.date(), s_data['annual_pay_periods'],
                                 context=context)
        
        # Attach payroll register to this pay period
        period_obj.write(cr, uid, period_id, {'register_id': register_id}, context=context)
        
        # Mark the pay period as being in the payroll generation stage
        netsvc.LocalService('workflow').trg_validate(uid, 'hr.payroll.period', period_id, 'generate_payslips', cr)
        
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.payroll.period.end.1',
            'type': 'ir.actions.act_window',
            'target': 'inline',
            'context': context
        }
    
    def view_benefit_premiums(self, cr, uid, ids, context=None):
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id:
            return {'type': 'ir.actions.act_window_close'}
        
        p_data = self.pool.get('hr.payroll.period').read(cr, uid, period_id, ['register_id'],
                                                         context=context)
        run_obj = self.pool.get('hr.payslip.run')
        ps_obj = self.pool.get('hr.payslip')
        pay_obj = self.pool.get('hr.payslip.accrual')
        run_ids = run_obj.search(cr, uid, [('register_id', '=', p_data['register_id'][0])],
                                 context=context)
        ps_ids = ps_obj.search(cr, uid, [('payslip_run_id', 'in', run_ids)], context=context)
        pay_ids = pay_obj.search(cr, uid, [('payslip_id', 'in', ps_ids)], context=context)
        return {
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'hr.payslip.accrual',
            'domain': [('id', 'in', pay_ids)],
            'type': 'ir.actions.act_window',
            'target': 'new',
            'nodestroy': True,
            'context': context,
        }
    
    def create_payslip_runs(self, cr, uid, register_id, dept_ids, contract_ids,
                            date_start, date_end, annual_pay_periods, context=None):
        
        contract_obj = self.pool.get('hr.contract')
        dept_obj = self.pool.get('hr.department')
        ee_obj = self.pool.get('hr.employee')
        slip_obj = self.pool.get('hr.payslip')
        run_obj = self.pool.get('hr.payslip.run')
        pp_obj = self.pool.get('hr.payroll.period')
        
        # Get Pay Slip Amendments, Employee ID, and the amount of the amendment
        #
        psa_codes = []
        psa_ids = self._get_confirmed_amendments(cr, uid, context)
        for psa in self.pool.get('hr.payslip.amendment').browse(cr, uid, psa_ids, context=context):
            psa_codes.append((psa.employee_id.id, psa.input_id.code, psa.amount))
        
        # Keep track of employees that have already been included
        seen_ee_ids = []
        
        # Create payslip batch (run) for each department
        #
        for dept in dept_obj.browse(cr, uid, dept_ids, context=context):
            ee_ids = []
            c_ids = contract_obj.search(cr, uid, [('id', 'in', contract_ids),
                                                  ('date_start', '<=', date_end.strftime(OEDATE_FORMAT)),
                                                  ('date_end', '>=', date_start.strftime(OEDATE_FORMAT)),
                                                  '|', ('department_id.id', '=', dept.id),
                                                       ('employee_id.department_id.id', '=', dept.id),
                                                 ], context=context)
            c2_ids = contract_obj.search(cr, uid, [('id', 'in', contract_ids),
                                                   ('date_start', '<=', date_end.strftime(OEDATE_FORMAT)),
                                                   ('date_end', '>=', date_start.strftime(OEDATE_FORMAT)),
                                                   ('employee_id.status', 'in', ['pending_inactive', 'inactive']),
                                                   '|', ('job_id.department_id.id', '=', dept.id),
                                                        ('end_job_id.department_id.id', '=', dept.id),
                                                  ], context=context)
            for i in c2_ids:
                if i not in c_ids:
                    c_ids.append(i)
            
            c_data = contract_obj.read(cr, uid, c_ids, ['employee_id'], context=context)
            for data in c_data:
                if data['employee_id'][0] not in ee_ids:
                    ee_ids.append(data['employee_id'][0])

            if len(ee_ids) == 0:
                continue
            
            # Alphabetize
            ee_ids = ee_obj.search(cr, uid, [('id', 'in', ee_ids),
                                             '|', ('active', '=', False), ('active', '=', True)],
                                   context=context)
            
            run_res = {
                'name': dept.complete_name,
                'date_start': date_start,
                'date_end': date_end,
                'register_id': register_id,
            }
            run_id = run_obj.create(cr, uid, run_res, context=context)
         
            # Create a pay slip for each employee in each department that has
            # a contract in the pay period schedule of this pay period
            #   
            slip_ids = []
            for ee in ee_obj.browse(cr, uid, ee_ids, context=context):
                
                if ee.id in seen_ee_ids:
                    continue
                
                slip_id = pp_obj.create_payslip(cr, uid, ee.id, date_start, date_end, psa_codes,
                                                run_id, annual_pay_periods, context=context)
                if slip_id != False:
                    slip_ids.append(slip_id)
                
                seen_ee_ids.append(ee.id)
            
            # Calculate payroll for all the pay slips in this batch (run)
            slip_obj.compute_sheet(cr, uid, slip_ids, context=context)
        
        return
    
    def view_payroll_register(self, cr, uid, ids, context=None):
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id:
            return {'type': 'ir.actions.act_window_close'}
        
        p_data = self.pool.get('hr.payroll.period').read(cr, uid, period_id, ['register_id'],
                                                         context=context)
        
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.payroll.register',
            'res_id': p_data['register_id'][0],
            'type': 'ir.actions.act_window',
            'target': 'current',
            'nodestroy': True,
            'context': context,
        }

    def start_payments(self, cr, uid, ids, context=None):
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id:
            return {'type': 'ir.actions.act_window_close'}
        
        # Do not continue if there are still any critical payroll exceptions
        #
        data = self.read(cr, uid, ids[0], ['pex_critical'], context=context)
        if data.get('pex_critical') != 0:
            raise osv.except_osv(_('Unable to Start Payments'), _('There are one or more Critical Payroll Exceptions. Please correct them before proceeding.'))
        
        p_data = self.pool.get('hr.payroll.period').read(cr, uid, period_id,
                                                         ['state', 'register_id'],
                                                         context=context)
        if p_data['state'] != 'generate':
            return {'type': 'ir.actions.act_window_close'}
        
        wkf_service = netsvc.LocalService('workflow')
        
        # Set Pay Slip Amendments to Done
        #
        psa_ids = self._get_confirmed_amendments(cr, uid, context)
        [wkf_service.trg_validate(uid, 'hr.payslip.amendment', psa_id, 'payslip_done', cr) for psa_id in psa_ids]
        
        # Verify Pay Slips
        #
        reg_obj = self.pool.get('hr.payroll.register')
        reg_data = reg_obj.read(cr, uid, p_data['register_id'][0], ['run_ids'], context=context)
        for run_id in reg_data['run_ids']:
            run_data = self.pool.get('hr.payslip.run').read(cr, uid, run_id,
                                                            ['slip_ids'], context=context)
            [wkf_service.trg_validate(uid, 'hr.payslip', slip_id, 'hr_verify_sheet', cr) for slip_id in run_data['slip_ids']]
        
        wkf_service.trg_validate(uid, 'hr.payroll.period', period_id, 'start_payments', cr)
        
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.payroll.period.end.1',
            'type': 'ir.actions.act_window',
            'target': 'inline',
            'context': context
        }
    
    def print_payslips(self, cr, uid, ids, context=None):
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id:
            return {'type': 'ir.actions.act_window_close'}
        
        p_data = self.pool.get('hr.payroll.period').read(cr, uid, period_id, ['register_id'],
                                                         context=context)
        
        return {
            'type': 'ir.actions.report.xml',
            'report_name': 'hr_payroll_register_payslip_report',
            'datas': {'ids': [p_data['register_id'][0]]},
        }
    
    def print_payroll_summary(self, cr, uid, ids, context=None):
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id:
            return {'type': 'ir.actions.act_window_close'}
        
        p_data = self.pool.get('hr.payroll.period').read(cr, uid, period_id, ['register_id'],
                                                         context=context)
        
        return {
            'type': 'ir.actions.report.xml',
            'report_name': 'hr.payroll.register.summary',
            'datas': {'ids': [p_data['register_id'][0]]},
        }
    
    def print_payroll_register(self, cr, uid, ids, context=None):
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id:
            return {'type': 'ir.actions.act_window_close'}
        
        p_data = self.pool.get('hr.payroll.period').read(cr, uid, period_id, ['register_id'],
                                                         context=context)
        
        return {
            'type': 'ir.actions.report.xml',
            'report_name': 'hr_payroll_register_report',
            'datas': {'ids': [p_data['register_id'][0]]},
        }
    
    def print_payslip_details(self, cr, uid, ids, context=None):
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id:
            return {'type': 'ir.actions.act_window_close'}
        
        p_data = self.pool.get('hr.payroll.period').read(cr, uid, period_id, ['register_id'],
                                                         context=context)
        register = self.pool.get('hr.payroll.register').browse(cr, uid, p_data['register_id'][0],
                                                               context=context)
        slip_ids = []
        for run in register.run_ids:
            [slip_ids.append(s.id) for s in run.slip_ids]
        
        return {
            'type': 'ir.actions.report.xml',
            'report_name': 'payslip',
            'datas': {'ids': slip_ids},
        }
    
    def print_contribution_registers(self, cr, uid, ids, context=None):
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id:
            return {'type': 'ir.actions.act_window_close'}
        
        data = self.pool.get('hr.payroll.period').read(cr, uid, period_id, ['date_start', 'date_end'],
                                                       context=context)
        register_ids = self.pool.get('hr.contribution.register').search(cr, uid, [], context=context)
        
        form = {'date_from': data['date_start'],
                'date_to': data['date_end'],}
        
        return {
            'type': 'ir.actions.report.xml',
            'report_name': 'contribution.register.lines',
            'datas': {'ids': register_ids, 'form': form, 'model': 'hr.contribution.register'},
        }
    
    def close_pay_period(self, cr, uid, ids, context=None):
        
        if context == None: context = {}
        period_id = context.get('active_id', False)
        if not period_id:
            return {'type': 'ir.actions.act_window_close'}
        
        p_data = self.pool.get('hr.payroll.period').read(cr, uid, period_id,
                                                         ['state'],
                                                         context=context)
        if p_data['state'] != 'payment':
            return {'type': 'ir.actions.act_window_close'}
        
        wkf_service = netsvc.LocalService('workflow')
        wkf_service.trg_validate(uid, 'hr.payroll.period', period_id, 'close_period', cr)
        
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.payroll.period',
            'type': 'ir.actions.act_window',
            'target': 'current',
            'context': context
        }
