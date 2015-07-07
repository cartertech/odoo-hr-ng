#-*- coding:utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015 One Click Software (http://oneclick.solutions)
#    and Copyright (C) 2011, 2013 Michael Telahun Makonnen <mmakonnen@gmail.com>.
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

import calendar
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from pytz import common_timezones, timezone, utc

import openerp.netsvc
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as OE_DFORMAT
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT as OE_DTFORMAT
from openerp.tools.safe_eval import safe_eval as eval
from openerp.tools.translate import _
from openerp.osv import fields, osv

import logging
_logger = logging.getLogger(__name__)

# Obtained from: http://stackoverflow.com/questions/4130922/how-to-increment-datetime-month-in-python
#
def add_months(sourcedate, months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month / 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return datetime(year,month,day)

def get_period_year(dt, annual_pay_periods):
    
    month_number = 0
    year_number = 0
    if dt.day < 15:
        month_number = dt.month
        year_number = dt.year
    else:
        dtTmp = add_months(dt, 1)
        month_number = dtTmp.month
        year_number = dtTmp.year
    return month_number, year_number

class hr_payroll_period(osv.osv):
    
    _name = 'hr.payroll.period'
    
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    
    _columns = {
        'name': fields.char('Description', size=256, required=True),
        'schedule_id': fields.many2one('hr.payroll.period.schedule', 'Payroll Period Schedule',
                                       required=True),
        'date_start': fields.datetime('Start Date', required=True),
        'date_end': fields.datetime('End Date', required=True),
        'register_id': fields.many2one('hr.payroll.register', 'Payroll Register', readonly=True,
                                       states={'generate': [('readonly', False)]}),
        'state': fields.selection([('open', 'Open'),
                                   ('ended', 'End of Period Processing'),
                                   ('locked', 'Locked'),
                                   ('generate', 'Generating Payslips'),
                                   ('payment', 'Payment'),
                                   ('closed', 'Closed')],
                                  'State', select=True, readonly=True),
    }
    
    _order = "date_start, name desc"
    
    _defaults = {
        'state': 'open',
    }
    
    _track = {
        'state': {
            'hr_payroll_period.mt_state_open': lambda self, cr, uid, obj, ctx=None: obj['state'] == 'open',
            'hr_payroll_period.mt_state_end': lambda self, cr, uid, obj, ctx=None: obj['state'] == 'ended',
            'hr_payroll_period.mt_state_lock': lambda self, cr, uid, obj, ctx=None: obj['state'] == 'locked',
            'hr_payroll_period.mt_state_generate': lambda self, cr, uid, obj, ctx=None: obj['state'] == 'generate',
            'hr_payroll_period.mt_state_payment': lambda self, cr, uid, obj, ctx=None: obj['state'] == 'payment',
            'hr_payroll_period.mt_state_close': lambda self, cr, uid, obj, ctx=None: obj['state'] == 'closed',
        },
    }
    
    def _needaction_domain_get(self, cr, uid, context=None):
        
        users_obj = self.pool.get('res.users')
        domain = []
        
        if users_obj.has_group(cr, uid, 'hr_security.group_payroll_manager'):
            domain = [('state', 'not in', ['open', 'closed'])]
            return domain
        
        return False
    
    def is_ended(self, cr, uid, period_id, context=None):
        
        #
        # XXX - Someone who cares about DST should update this code to handle it.
        #
        
        flag = False
        if period_id:
            utc_tz = timezone('UTC')
            utcDtNow = utc_tz.localize(datetime.now(), is_dst=False)
            period = self.browse(cr, uid, period_id, context=context)
            if period:
                dtEnd = datetime.strptime(period.date_end, '%Y-%m-%d %H:%M:%S')
                utcDtEnd = utc_tz.localize(dtEnd, is_dst=False)
                if utcDtNow > utcDtEnd + timedelta(minutes=(period.schedule_id.ot_max_rollover_hours * 60)):
                    flag = True
        return flag
    
    def try_signal_end_period(self, cr, uid, context=None):
        """Method called, usually by cron, to transition any payroll periods
        that are past their end date.
        """
        
        #
        # XXX - Someone who cares about DST should update this code to handle it.
        #
        
        utc_tz = timezone('UTC')
        utcDtNow = utc_tz.localize(datetime.now(), is_dst=False)
        period_ids = self.search(cr, uid, [
                                           ('state','in',['open']),
                                           ('date_end','<=',utcDtNow.strftime('%Y-%m-%d %H:%M:%S')),
                                          ], context=context)
        if len(period_ids) == 0:
            return
        
        wf_service = netsvc.LocalService('workflow')
        for pid in period_ids:
            wf_service.trg_validate(uid, 'hr.payroll.period', pid, 'end_period', cr)
    
    def get_utc_times(self, cr, uid, period, context=None):
        
        #
        # XXX - Someone who cares about DST should update this code to handle it.
        #
        
        utc_tz = timezone('UTC')
        dt = datetime.strptime(period.date_start, OE_DTFORMAT)
        utcDtStart = utc_tz.localize(dt, is_dst=False)
        dt = datetime.strptime(period.date_end, OE_DTFORMAT)
        utcDtEnd = utc_tz.localize(dt, is_dst=False)
        
        return (utcDtStart, utcDtEnd)
    
    def lock_period(self, cr, uid, periods, employee_ids, context=None):
        
        wkf_service = netsvc.LocalService('workflow')
        attendance_obj = self.pool.get('hr.attendance')
        detail_obj = self.pool.get('hr.schedule.detail')
        holiday_obj = self.pool.get('hr.holidays')
        for period in periods:
            utcDtStart, utcDtEnd = self.get_utc_times(cr, uid, period, context=context)
            
            # Lock sign-in and sign-out attendance records
            punch_ids = attendance_obj.search(cr, uid, [
                                                        ('employee_id', 'in', employee_ids),
                                                        '&', ('name','>=', utcDtStart.strftime(OE_DTFORMAT)),
                                                             ('name','<=', utcDtEnd.strftime(OE_DTFORMAT)),
                                                       ], order='name', context=context)
            [wkf_service.trg_validate(uid, 'hr.attendance', pid, 'signal_lock', cr) for pid in punch_ids]
            
            # Lock schedules
            detail_ids = detail_obj.search(cr, uid, [
                                                     ('schedule_id.employee_id', 'in', employee_ids),
                                                     '&', ('date_start','>=', utcDtStart.strftime(OE_DTFORMAT)),
                                                          ('date_start','<=', utcDtEnd.strftime(OE_DTFORMAT)),
                                                    ], order='date_start', context=context)
            [wkf_service.trg_validate(uid, 'hr.schedule.detail', did, 'signal_lock', cr) for did in detail_ids]
            
            # Lock holidays/leaves that end in the current period
            holiday_ids = holiday_obj.search(cr, uid, [
                                                       ('employee_id', 'in', employee_ids),
                                                       '&', ('date_to', '>=', utcDtStart.strftime(OE_DTFORMAT)),
                                                            ('date_to', '<=', utcDtEnd.strftime(OE_DTFORMAT)),
                                                      ],
                                             context=context)
            holiday_obj.write(cr, uid, holiday_ids, {'payroll_period_state': 'locked'},
                              context=context)
        
        return
    
    def unlock_period(self, cr, uid, periods, employee_ids, context=None):
        
        wkf_service = netsvc.LocalService('workflow')
        attendance_obj = self.pool.get('hr.attendance')
        detail_obj = self.pool.get('hr.schedule.detail')
        holiday_obj = self.pool.get('hr.holidays')
        for period in periods:
            utcDtStart, utcDtEnd = self.get_utc_times(cr, uid, period, context=context)
            
            # Unlock attendance
            punch_ids = attendance_obj.search(cr, uid, [
                                                        ('employee_id','in',employee_ids),
                                                        '&', ('name','>=', utcDtStart.strftime(OE_DTFORMAT)),
                                                             ('name','<=', utcDtEnd.strftime(OE_DTFORMAT)),
                                                       ], order='name', context=context)
            [wkf_service.trg_validate(uid, 'hr.attendance', pid, 'signal_unlock' ,cr) for pid in punch_ids]
            
            # Unlock schedules
            detail_ids = detail_obj.search(cr, uid, [
                                                        ('schedule_id.employee_id','in',employee_ids),
                                                        '&', ('date_start','>=', utcDtStart.strftime(OE_DTFORMAT)),
                                                             ('date_start','<=', utcDtEnd.strftime(OE_DTFORMAT)),
                                                    ], order='date_start', context=context)
            [wkf_service.trg_validate(uid, 'hr.schedule.detail', did, 'signal_unlock' ,cr) for did in detail_ids]
            
            # Unlock holidays/leaves that end in the current period
            holiday_ids = holiday_obj.search(cr, uid, [
                                                        ('employee_id', 'in', employee_ids),
                                                        '&', ('date_to', '>=', utcDtStart.strftime(OE_DTFORMAT)),
                                                             ('date_to', '<=', utcDtEnd.strftime(OE_DTFORMAT)),
                                                      ],
                                             context=context)
            holiday_obj.write(cr, uid, holiday_ids, {'payroll_period_state': 'unlocked'},
                              context=context)
        
        return
    
    def set_state_ended(self, cr, uid, ids, context=None):
        
        for period in self.browse(cr, uid, ids, context=context):
            if period.state in ['locked', 'generate']:
                
                employee_ids = []
                for contract in period.schedule_id.contract_ids:
                    if contract.employee_id.id not in employee_ids:
                        employee_ids.append(contract.employee_id.id)
                        
                self.unlock_period(cr, uid, [period], employee_ids, context)
            
            self.write(cr, uid, period.id, {'state': 'ended'}, context=context)
        
        return True
    
    def set_state_locked(self, cr, uid, ids, context=None):
        
        for period in self.browse(cr, uid, ids, context=context):
            
            employee_ids = []
            for contract in period.schedule_id.contract_ids:
                if contract.employee_id.id not in employee_ids:
                    employee_ids.append(contract.employee_id.id)
            
            self.lock_period(cr, uid, [period], employee_ids, context=context)
            
            self.write(cr, uid, period.id, {'state': 'locked'}, context=context)
        
        return True
        
    def set_state_closed(self, cr, uid, ids, context=None):
        
        # When we close a pay period, also de-activate related attendances
        #
        attendance_obj = self.pool.get('hr.attendance')
        for period in self.browse(cr, uid, ids, context=context):
            #
            # XXX - Someone who cares about DST should update this code to handle it.
            #
            utc_tz = timezone('UTC')
            dt = datetime.strptime(period.date_start, '%Y-%m-%d %H:%M:%S')
            utcDtStart = utc_tz.localize(dt, is_dst=False)
            dt = datetime.strptime(period.date_end, '%Y-%m-%d %H:%M:%S')
            utcDtEnd = utc_tz.localize(dt, is_dst=False)
            for contract in period.schedule_id.contract_ids:
                employee = contract.employee_id
                
                # De-activate sign-in and sign-out attendance records
                punch_ids = attendance_obj.search(cr, uid, [
                                                            ('employee_id','=',employee.id),
                                                            '&', ('name','>=', utcDtStart.strftime('%Y-%m-%d %H:%M:%S')),
                                                                 ('name','<=', utcDtEnd.strftime('%Y-%m-%d %H:%M:%S')),
                                                           ], order='name', context=context)
                attendance_obj.write(cr, uid, punch_ids, {'active': False}, context=context)
        
        return self.write(cr, uid, ids, {'state': 'closed'}, context=context)
    
    def create_payslip(self, cr, uid, employee_id, dPeriodStart, dPeriodEnd,
                       payslip_amendments=[], run_id=False, annual_pay_periods=12, context=None):
        
        slip_obj = self.pool.get('hr.payslip')

        found_contracts = []
        dEarliestContractStart = False
        dLastContractEnd = False
        open_contract = False
        ee = self.pool.get('hr.employee').browse(cr, uid, employee_id, context=context)
        for contract in ee.contract_ids:
        
            # Does employee have a contract in this pay period?
            #
            dContractStart = datetime.strptime(contract.date_start, OE_DFORMAT).date()
            dContractEnd = False
            if contract.date_end:
                dContractEnd = datetime.strptime(contract.date_end, OE_DFORMAT).date()
            if dContractStart > dPeriodEnd or (dContractEnd and dContractEnd < dPeriodStart):
                continue
            else:
                found_contracts.append(contract)
                if not dEarliestContractStart or dContractStart < dEarliestContractStart:
                    dEarliestContractStart = dContractStart
                if not dContractEnd:
                    dLastContractEnd = False
                    open_contract = True
                elif not open_contract and dContractEnd and (not dLastContractEnd or dContractEnd > dLastContractEnd):
                    dLastContractEnd = dContractEnd
        
        if len(found_contracts) == 0:
            return False
        
        # If the contract doesn't cover the full pay period use the contract
        # dates as start/end dates instead of the full period.
        #
        period_start_date = dPeriodStart.strftime(OE_DFORMAT)
        period_end_date = dPeriodEnd.strftime(OE_DFORMAT)
        temp_date_start = period_start_date
        temp_date_end = period_end_date
        if dEarliestContractStart > datetime.strptime(period_start_date, OE_DFORMAT).date():
            temp_date_start = dEarliestContractStart.strftime(OE_DFORMAT)
        if dLastContractEnd and dLastContractEnd < datetime.strptime(period_end_date, OE_DFORMAT).date():
            temp_date_end = dLastContractEnd.strftime(OE_DFORMAT)
        
        # If termination procedures have begun within the contract period, use the
        # effective date of the termination as the end date.
        #
        term_obj = self.pool.get('hr.employee.termination')
        term_ids = term_obj.search(cr, uid, [('employee_id', '=', found_contracts[0].employee_id.id),
                                             ('employee_id.status', 'in', ['pending_inactive', 'inactive']),
                                             ('state', 'in', ['draft','confirm', 'done'])],
                                   context=context)
        if len(term_ids) > 0:
            term_data = term_obj.read(cr, uid, term_ids, ['name'], context=context)
            for data in term_data:
                if data['name'] >= temp_date_start and data['name'] < temp_date_end:
                    temp_date_end = data['name']
        
        slip_data = slip_obj.onchange_employee_id(cr, uid, [],
                                                  temp_date_start, temp_date_end,
                                                  ee.id, contract_id=False,
                                                  context=context)
        
        # Make modifications to rule inputs
        #
        for line in slip_data['value'].get('input_line_ids', False):
            
            # Pay Slip Amendment modifications
            for eid, code, amount in payslip_amendments:
                # count the number of times this input rule appears (this
                # is dependent on no. of contracts in pay period), and
                # distribute the total amount equally among them.
                #
                rule_count = 0
                for _l2 in slip_data['value']['input_line_ids']:
                    if eid == ee.id and _l2['code'] == code:
                        rule_count += 1
                if eid == ee.id and line['code'] == code:
                    line['amount'] = amount / float(rule_count)
                    break
        
        month_no, year_no = get_period_year(dPeriodStart, annual_pay_periods)
        slip_name = _("Pay Slip %s/%s") % (year_no, month_no)
        res = {
            'employee_id': ee.id,
            'name': slip_name,
            'struct_id': slip_data['value'].get('struct_id', False),
            'contract_id': slip_data['value'].get('contract_id', False),
            'payslip_run_id': run_id,
            'input_line_ids': [(0, 0, x) for x in slip_data['value'].get('input_line_ids', False)],
            'worked_days_line_ids': [(0, 0, x) for x in slip_data['value'].get('worked_days_line_ids', False)],
            'date_from': period_start_date,
            'date_to': period_end_date
        }
        
        return slip_obj.create(cr, uid, res, context=context)

class hr_payperiod_schedule(osv.osv):
    
    _name = 'hr.payroll.period.schedule'
    
    def _tz_list(self, cr, uid, context=None):
        
        res = tuple()
        for name in common_timezones:
            res += ((name, name),)
        return res
    
    def _calculate_annual_periods(self, cr, uid, ids, field_name, arg, context=None):
        
        res = dict.fromkeys(ids, 0)
        for pps in self.browse(cr, uid, ids, context=context):
            if pps.type == 'manual':
                res[pps.id] = 0
            elif pps.type == 'monthly':
                res[pps.id] = 12
        return res
    
    _columns = {
        'name': fields.char('Description', size=256, required=True),
        'tz': fields.selection(_tz_list, 'Time Zone', required=True),
        'paydate_biz_day': fields.boolean('Pay Date on a Business Day'),
        'ot_week_startday': fields.selection([
                                              ('0', _('Sunday')),
                                              ('1', _('Monday')),
                                              ('2', _('Tuesday')),
                                              ('3', _('Wednesday')),
                                              ('4', _('Thursday')),
                                              ('5', _('Friday')),
                                              ('6', _('Saturday')),
                                             ],
                                             'Start of Week', required=True),
        'ot_max_rollover_hours': fields.integer('OT Max. Continous Hours', required=True),
        'ot_max_rollover_gap': fields.integer('OT Max. Continuous Hours Gap (in Min.)', required=True),
        'type': fields.selection([
                                  ('manual', 'Manual'),
                                  ('monthly', 'Monthly'),
                                 ],
                                 'Type', required=True),
        'annual_pay_periods': fields.function(_calculate_annual_periods, type='integer', string='Annual Pay Periods'),
        'mo_firstday': fields.selection([
                                         ('1', '1'),('2', '2'),('3', '3'),('4', '4'),('5', '5'),('6', '6'),('7', '7'),
                                         ('8', '8'),('9', '9'),('10', '10'),('11', '11'),('12', '12'),('13', '13'),('14', '14'),
                                         ('15', '15'),('16', '16'),('17', '17'),('18', '18'),('19', '19'),('20', '20'),('21', '21'),
                                         ('22', '22'),('23', '23'),('24', '24'),('25', '25'),('26', '26'),('27', '27'),('28', '28'),
                                         ('29', '29'),('30', '30'),('31', '31'),
                                        ],
                                        'Start Day'),
        'mo_paydate': fields.selection([
                                        ('1', '1'),('2', '2'),('3', '3'),('4', '4'),('5', '5'),('6', '6'),('7', '7'),
                                        ('8', '8'),('9', '9'),('10', '10'),('11', '11'),('12', '12'),('13', '13'),('14', '14'),
                                        ('15', '15'),('16', '16'),('17', '17'),('18', '18'),('19', '19'),('20', '20'),('21', '21'),
                                        ('22', '22'),('23', '23'),('24', '24'),('25', '25'),('26', '26'),('27', '27'),('28', '28'),
                                        ('29', '29'),('30', '30'),('31', '31'),
                                       ],
                                       'Pay Date'),
        'contract_ids': fields.one2many('hr.contract', 'pps_id', 'Contracts'),
        'pay_period_ids': fields.one2many('hr.payroll.period', 'schedule_id', 'Pay Periods'),
        'initial_period_date': fields.date('Initial Period Start Date'),
        'active': fields.boolean('Active'),
    }
    
    _defaults = {
        'ot_week_startday': '1',
        'ot_max_rollover_hours': 6,
        'ot_max_rollover_gap': 60,
        'mo_firstday': '1',
        'mo_paydate': '3',
        'type': 'monthly',
        'active': True,
    }
    
    def _check_initial_date(self, cr, uid, ids, context=None):
        
        for obj in self.browse(cr, uid, ids, context=context):
            if obj.type in ['monthly'] and not obj.initial_period_date:
                return False
        
        return True
    
    _constraints = [
        (_check_initial_date, 'You must supply an Initial Period Start Date', ['type']),
    ]
    
    def add_pay_period(self, cr, uid, ids, context=None):
        
        #
        # XXX - Someone who cares about DST should update this code to handle it.
        #
        
        schedule_obj = self.pool.get('hr.payroll.period.schedule')
        
        data = None
        latest = None
        for sched in schedule_obj.browse(cr, uid, ids, context=context):
            for p in sched.pay_period_ids:
                if not latest:
                    latest = p
                    continue
                if datetime.strptime(p.date_end, '%Y-%m-%d %H:%M:%S') > datetime.strptime(latest.date_end, '%Y-%m-%d %H:%M:%S'):
                    latest = p
            local_tz = timezone(sched.tz)
            if not latest:
                # No pay periods have been defined yet for this pay period schedule.
                if sched.type == 'monthly':
                    dtStart = datetime.strptime(sched.initial_period_date, '%Y-%m-%d')
                    if dtStart.day > int(sched.mo_firstday):
                        dtStart = add_months(dtStart, 1)
                        dtStart = datetime(dtStart.year, dtStart.month, int(sched.mo_firstday), 0, 0, 0)
                    elif dtStart.day < int(sched.mo_firstday):
                        dtStart = datetime(dtStart.year, dtStart.month, int(sched.mo_firstday), 0, 0, 0)
                    else:
                        dtStart = datetime(dtStart.year, dtStart.month, dtStart.day, 0, 0, 0)
                    dtEnd = add_months(dtStart, 1) - timedelta(days=1)
                    dtEnd = datetime(dtEnd.year, dtEnd.month, dtEnd.day, 23, 59, 59)
                    month_number, year_number = get_period_year(dtStart, 12)
                    
                    # Convert from time zone of punches to UTC for storage
                    utcStart = local_tz.localize(dtStart, is_dst=None)
                    utcStart = utcStart.astimezone(utc)
                    utcEnd = local_tz.localize(dtEnd, is_dst=None)
                    utcEnd = utcEnd.astimezone(utc)

                    data = {
                        'name': 'Pay Period ' + str(month_number) + '/' + str(year_number),
                        'schedule_id': sched.id,
                        'date_start': utcStart.strftime('%Y-%m-%d %H:%M:%S'),
                        'date_end': utcEnd.strftime('%Y-%m-%d %H:%M:%S'),
                    }
            else:
                if sched.type == 'monthly':
                    # Convert from UTC to timezone of punches
                    utcStart = datetime.strptime(latest.date_end, '%Y-%m-%d %H:%M:%S')
                    utc_tz = timezone('UTC')
                    utcStart = utc_tz.localize(utcStart, is_dst=None)
                    utcStart += timedelta(seconds=1)
                    dtStart = utcStart.astimezone(local_tz)
                    
                    # Roll forward to the next pay period start and end times
                    dtEnd = add_months(dtStart, 1) - timedelta(days=1)
                    dtEnd = datetime(dtEnd.year, dtEnd.month, dtEnd.day, 23, 59, 59)
                    month_number, year_number = get_period_year(dtStart, 12)
                    
                    # Convert from time zone of punches to UTC for storage
                    utcStart = dtStart.astimezone(utc_tz)
                    utcEnd = local_tz.localize(dtEnd, is_dst=None)
                    utcEnd = utcEnd.astimezone(utc)
                    
                    data = {
                        'name': 'Pay Period ' + str(month_number) + '/' + str(year_number),
                        'schedule_id': sched.id,
                        'date_start': utcStart.strftime('%Y-%m-%d %H:%M:%S'),
                        'date_end': utcEnd.strftime('%Y-%m-%d %H:%M:%S'),
                    }
            if data != None:
                schedule_obj.write(cr, uid, sched.id, {'pay_period_ids': [(0, 0, data)]}, context=context)
    
    def _get_latest_period(self, cr, uid, sched_id, context=None):
        
        sched = self.browse(cr, uid, sched_id, context=context)
        latest_period = False
        for period in sched.pay_period_ids:
            if not latest_period:
                latest_period = period
                continue
            if datetime.strptime(period.date_end, '%Y-%m-%d %H:%M:%S') > datetime.strptime(latest_period.date_end, '%Y-%m-%d %H:%M:%S'):
                latest_period = period
        
        return latest_period
    
    def try_create_new_period(self, cr, uid, context=None):
        '''Try and create pay periods for up to 3 months from now.'''
        
        #
        # XXX - Someone who cares about DST should update this code to handle it.
        #
        
        dtNow = datetime.now()
        utc_tz = timezone('UTC')
        sched_obj = self.pool.get('hr.payroll.period.schedule')
        sched_ids = sched_obj.search(cr, uid, [], context=context)
        for sched in sched_obj.browse(cr, uid, sched_ids, context=context):
            if sched.type == 'monthly':
                firstday = sched.mo_firstday
            else:
                continue
            dtNow = datetime.strptime(dtNow.strftime('%Y-%m-' + firstday + ' 00:00:00'), '%Y-%m-%d %H:%M:%S')
            loclDTNow = timezone(sched.tz).localize(dtNow, is_dst=False)
            utcDTFuture = loclDTNow.astimezone(utc_tz) + relativedelta(months= +3)
            
            if not sched.pay_period_ids:
                self.add_pay_period(cr, uid, [sched.id], context=context)
            
            latest_period = self._get_latest_period(cr, uid, sched.id, context=context)
            utcDTStart = utc_tz.localize(datetime.strptime(latest_period.date_start, '%Y-%m-%d %H:%M:%S'), is_dst=False)
            while utcDTFuture > utcDTStart:
                self.add_pay_period(cr, uid, [sched.id], context=context)            
                latest_period = self._get_latest_period(cr, uid, sched.id, context=context)
                utcDTStart = utc_tz.localize(datetime.strptime(latest_period.date_start, '%Y-%m-%d %H:%M:%S'), is_dst=False)

class contract_init(osv.Model):
    
    _inherit = 'hr.contract.init'
    
    _columns = {
        'pay_sched_id': fields.many2one('hr.payroll.period.schedule', 'Payroll Period Schedule',
                                        readonly=True, states={'draft': [('readonly', False)]}),
    }

class hr_contract(osv.osv):
    
    _name = 'hr.contract'
    _inherit = 'hr.contract'
    
    _columns = {
        'pps_id': fields.many2one('hr.payroll.period.schedule', 'Payroll Period Schedule', required=True),
    }
    
    def _get_pay_sched(self, cr, uid, context=None):
        
        res = False
        init = self.get_latest_initial_values(cr, uid, context=context)
        if init != None and init.pay_sched_id:
            res = init.pay_sched_id.id
        return res
    
    _defaults = {
        'pps_id': _get_pay_sched,
    }

class hr_payslip(osv.osv):
    
    _name = 'hr.payslip'
    _inherit = 'hr.payslip'
    
    _columns = {
        'exception_ids': fields.one2many('hr.payslip.exception', 'slip_id',
                                         'Exceptions', readonly=True),
    }
    
    def compute_sheet(self, cr, uid, ids, context=None):
        
        super(hr_payslip, self).compute_sheet(cr, uid, ids, context=context)
        
        def _sum_salary_rule_category(localdict, category, amount):
            if category.parent_id:
                localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
            if category.code in localdict['categories'].dict:
                localdict['categories'].dict[category.code] = localdict['categories'].dict[category.code] + amount
            else:
                localdict['categories'].dict[category.code] = amount
            return localdict

        class BrowsableObject(object):
            def __init__(self, pool, cr, uid, employee_id, dict):
                self.pool = pool
                self.cr = cr
                self.uid = uid
                self.employee_id = employee_id
                self.dict = dict

            def __getattr__(self, attr):
                return attr in self.dict and self.dict.__getitem__(attr) or 0.0

        class InputLine(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""
            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = datetime.now().strftime('%Y-%m-%d')
                result = 0.0
                self.cr.execute("SELECT sum(amount) as sum\
                            FROM hr_payslip as hp, hr_payslip_input as pi \
                            WHERE hp.employee_id = %s AND hp.state = 'done' \
                            AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s",
                           (self.employee_id, from_date, to_date, code))
                res = self.cr.fetchone()[0]
                return res or 0.0

        class WorkedDays(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""
            def _sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = datetime.now().strftime('%Y-%m-%d')
                result = 0.0
                self.cr.execute("SELECT sum(number_of_days) as number_of_days, sum(number_of_hours) as number_of_hours\
                            FROM hr_payslip as hp, hr_payslip_worked_days as pi \
                            WHERE hp.employee_id = %s AND hp.state = 'done'\
                            AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s",
                           (self.employee_id, from_date, to_date, code))
                return self.cr.fetchone()

            def sum(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[0] or 0.0

            def sum_hours(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[1] or 0.0

        class Payslips(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""

            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = datetime.now().strftime('%Y-%m-%d')
                self.cr.execute("SELECT sum(case when hp.credit_note = False then (pl.total) else (-pl.total) end)\
                            FROM hr_payslip as hp, hr_payslip_line as pl \
                            WHERE hp.employee_id = %s AND hp.state = 'done' \
                            AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.slip_id AND pl.code = %s",
                            (self.employee_id, from_date, to_date, code))
                res = self.cr.fetchone()
                return res and res[0] or 0.0

        rule_obj = self.pool.get('hr.payslip.exception.rule')
        rule_ids = rule_obj.search(cr, uid, [('active','=',True)], context=context)
        rule_seq = []
        for i in rule_ids:
            data = rule_obj.read(cr, uid, i, ['sequence'], context=context)
            rule_seq.append((i, data['sequence']))
        sorted_rule_ids = [id for id, sequence in sorted(rule_seq, key=lambda x:x[1])]
        
        for payslip in self.browse(cr, uid, ids, context=context):
            payslip_obj = Payslips(self.pool, cr, uid, payslip.employee_id.id, payslip)
            
            categories = {}
            categories_obj = BrowsableObject(self.pool, cr, uid, payslip.employee_id.id, categories)
            
            worked_days = {}
            for line in payslip.worked_days_line_ids:
                worked_days[line.code] = line
            worked_days_obj = WorkedDays(self.pool, cr, uid, payslip.employee_id.id, worked_days)
            
            inputs = {}
            for line in payslip.input_line_ids:
                inputs[line.code] = line
            input_obj = InputLine(self.pool, cr, uid, payslip.employee_id.id, inputs)
            
            temp_dict = {}
            utils_dict = self.get_utilities_dict(cr, uid, payslip.contract_id, payslip, context=context)
            for k,v in utils_dict.iteritems():
                k_obj = BrowsableObject(self.pool, cr, uid, payslip.employee_id.id, v)
                temp_dict.update({k: k_obj})
            utils_obj = BrowsableObject(self.pool, cr, uid, payslip.employee_id.id, temp_dict)
            
            localdict = {'categories': categories_obj,
                         'payslip': payslip_obj,
                         'worked_days': worked_days_obj,
                         'inputs': input_obj,
                         'utils': utils_obj}
            localdict['result'] = None
            
            # Total the sum of the categories
            for line in payslip.details_by_salary_rule_category:
                localdict = _sum_salary_rule_category(localdict, line.salary_rule_id.category_id,
                                                      line.total)
            
            for rule in rule_obj.browse(cr, uid, sorted_rule_ids, context=context):
                if rule_obj.satisfy_condition(cr, uid, rule.id, localdict, context=context):
                    val = {
                        'name': rule.name,
                        'slip_id': payslip.id,
                        'rule_id': rule.id,
                    }
                    self.pool.get('hr.payslip.exception').create(cr, uid, val, context=context)
        
        return True

class hr_payslip_exception(osv.osv):
    
    _name = 'hr.payslip.exception'
    _description = 'Payroll Exception'
    
    _columns = {
        'name':fields.char('Name', size=256, required=True, readonly=True),
        'rule_id': fields.many2one('hr.payslip.exception.rule', 'Rule', ondelete='cascade', readonly=True),
        'slip_id': fields.many2one('hr.payslip', 'Pay Slip', ondelete='cascade', readonly=True),
        'severity': fields.related('rule_id', 'severity', type="char", string="Severity", store=True, readonly=True),
    }

# This is almost 100% lifted from hr_payroll/hr.salary.rule
# I ommitted the parts I don't use.
#
class hr_payslip_exception_rule(osv.osv):
    
    _name = 'hr.payslip.exception.rule'
    _description = 'Rules describing pay slips in an abnormal state'
    
    _columns = {
        'name':fields.char('Name', size=256, required=True),
        'code':fields.char('Code', size=64, required=True),
        'sequence': fields.integer('Sequence', required=True, help='Use to arrange calculation sequence', select=True),
        'active':fields.boolean('Active', help="If the active field is set to false, it will allow you to hide the rule without removing it."),
        'company_id':fields.many2one('res.company', 'Company'),
        'condition_select': fields.selection([('none', 'Always True'), ('python', 'Python Expression')], "Condition Based on", required=True),
        'condition_python':fields.text('Python Condition', readonly=False, help='The condition that triggers the exception.'),
        'severity': fields.selection((
                                      ('low', 'Low'),
                                      ('medium', 'Medium'),
                                      ('high', 'High'),
                                      ('critical', 'Critical'),
                                     ), 'Severity', required=True),
        'note':fields.text('Description'),
    }
    
    _defaults = {
        'active': True,
        'company_id': lambda self, cr, uid, context: self.pool.get('res.company')._company_default_get(cr, uid, 'hr.payslip.exception.rule', context=context),
        'sequence': 5,
        'severity': 'low',
        'condition_select': 'none',
        'condition_python':
'''
# Available variables:
#----------------------
# payslip: object containing the payslips
# contract: hr.contract object
# categories: object containing the computed salary rule categories (sum of amount of all rules belonging to that category).
# worked_days: object containing the computed worked days
# inputs: object containing the computed inputs

# Note: returned value have to be set in the variable 'result'

result = categories.GROSS.amount > categories.NET.amount''',
    }

    def satisfy_condition(self, cr, uid, rule_id, localdict, context=None):
        """
        @param rule_id: id of hr.payslip.exception.rule to be tested
        @param contract_id: id of hr.contract to be tested
        @return: returns True if the given rule match the condition for the given contract. Return False otherwise.
        """
        rule = self.browse(cr, uid, rule_id, context=context)

        if rule.condition_select == 'none':
            return True
        else: #python code
            try:
                eval(rule.condition_python, localdict, mode='exec', nocopy=True)
                return 'result' in localdict and localdict['result'] or False
            except:
                raise osv.except_osv(_('Error!'), _('Wrong python condition defined for payroll exception rule %s (%s).')% (rule.name, rule.code))

class hr_payslip_amendment(osv.osv):
    
    _name = 'hr.payslip.amendment'
    _inherit = 'hr.payslip.amendment'
    
    _columns = {
        'pay_period_id': fields.many2one('hr.payroll.period', 'Pay Period', domain=[('state', 'in', ['open','ended','locked','generate'])], required=False, readonly=True, states={'draft': [('readonly', False)], 'validate': [('required', True)], 'done': [('required', True)]}),
    }

class hr_holidays_status(osv.osv):
    
    _name = 'hr.holidays.status'
    _inherit = 'hr.holidays.status'
    
    _columns = {
        'code': fields.char('Code', size=16, required=True),
    }
    
    _sql_constraints = [('code_unique', 'UNIQUE(code)', 'Codes for leave types must be unique!')]

class hr_holidays(osv.Model):
    
    _name = 'hr.holidays'
    _inherit = 'hr.holidays'
    
    _columns = {
        'payroll_period_state': fields.selection([('unlocked', 'Unlocked'), ('locked', 'Locked')],
                                                 'Payroll Period State', readonly=True),
    }
    
    _defaults = {
        'payroll_period_state': 'unlocked',
    }
    
    def unlink(self, cr, uid, ids, context=None):
        for h in self.browse(cr, uid, ids, context=context):
            if h.payroll_period_state == 'locked':
                raise osv.except_osv(_('Warning!'),
                                     _('You cannot delete a leave which belongs to a payroll period that has been locked.'))
        return super(hr_holidays, self).unlink(cr, uid, ids, context)

    def write(self, cr, uid, ids, vals, context=None):
        for h in self.browse(cr, uid, ids, context=context):
            if h.payroll_period_state == 'locked' and not vals.get('payroll_period_state', False):
                raise osv.except_osv(_('Warning!'),
                                     _('You cannot modify a leave which belongs to a payroll period that has been locked.'))
        return super(hr_holidays, self).write(cr, uid, ids, vals, context=context)
