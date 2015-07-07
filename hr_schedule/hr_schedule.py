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

import math
import time

import openerp.netsvc

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from pytz import timezone, utc

from openerp.osv import fields, osv
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT as OE_DTFORMAT
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as OE_DFORMAT
from openerp.tools.translate import _

DAYOFWEEK_SELECTION = [('0','Monday'),
                       ('1','Tuesday'),
                       ('2','Wednesday'),
                       ('3','Thursday'),
                       ('4','Friday'),
                       ('5','Saturday'),
                       ('6','Sunday'),
]

class week_days(osv.Model):
    
    _name = 'hr.schedule.weekday'
    _description = 'Days of the Week'
    
    _columns = {
        'name': fields.char('Name', size=64, required=True),
        'sequence': fields.integer('Sequence', required=True),
    }

class hr_schedule(osv.osv):
    
    _name = 'hr.schedule'
    _inherit = ['mail.thread']
    _description = 'Employee Schedule'
    
    def _compute_alerts(self, cr, uid, ids, field_name, args, context=None):
        res = dict.fromkeys(ids, '')
        for obj in self.browse(cr, uid, ids, context=context):
            alert_ids = []
            for detail in obj.detail_ids:
                [alert_ids.append(a.id) for a in detail.alert_ids]
            res[obj.id] = alert_ids
        return res
    
    _columns = {
        'name' : fields.char("Description", size=64, required=True, readonly=True, states={'draft': [('readonly',False)]}),
        'company_id' : fields.many2one('res.company', 'Company', readonly=True),
        'employee_id': fields.many2one('hr.employee', 'Employee', required=True, readonly=True, states={'draft': [('readonly',False)]}),
        'template_id': fields.many2one('hr.schedule.template', 'Schedule Template', readonly=True, states={'draft': [('readonly',False)]}),
        'detail_ids': fields.one2many('hr.schedule.detail', 'schedule_id', 'Schedule Detail', readonly=True, states={'draft': [('readonly',False)]}),
        'date_start': fields.date('Start Date', required=True, readonly=True, states={'draft': [('readonly',False)]}),
        'date_end': fields.date('End Date', required=True, readonly=True, states={'draft': [('readonly',False)]}),
        'department_id': fields.related('employee_id', 'department_id', type='many2one',
                                        relation='hr.department', string='Department', readonly=True,
                                        store={'hr.schedule': (lambda s, cr, u, ids, ctx: ids, ['employee_id'], 10)}),
        'alert_ids': fields.function(_compute_alerts, type='one2many', relation='hr.schedule.alert', string='Alerts', method=True, readonly=True),
        'restday_ids1': fields.many2many('hr.schedule.weekday', 'schedule_restdays_rel1', 'sched_id',
                                        'weekday_id', string='Rest Days Week 1'),
        'restday_ids2': fields.many2many('hr.schedule.weekday', 'schedule_restdays_rel2', 'sched_id',
                                        'weekday_id', string='Rest Days Week 2'),
        'restday_ids3': fields.many2many('hr.schedule.weekday', 'schedule_restdays_rel3', 'sched_id',
                                        'weekday_id', string='Rest Days Week 3'),
        'restday_ids4': fields.many2many('hr.schedule.weekday', 'schedule_restdays_rel4', 'sched_id',
                                        'weekday_id', string='Rest Days Week 4'),
        'restday_ids5': fields.many2many('hr.schedule.weekday', 'schedule_restdays_rel5', 'sched_id',
                                        'weekday_id', string='Rest Days Week 5'),
        'schedule_ot_ids': fields.one2many('hr.schedule.ot', 'schedule_id', 'Scheduled OT'),
        'state': fields.selection((
                                   ('draft', 'Draft'), ('validate', 'Confirmed'),
                                   ('locked', 'Locked'), ('unlocked', 'Unlocked'),
                                  ), 'State', required=True, readonly=True),
    }
    
    _defaults = {
        'company_id': lambda self, cr, uid, context: self.pool.get('res.company')._company_default_get(cr, uid, 'hr.schedule', context=context),
        'state': 'draft',
    }
    
    def _schedule_date(self, cr, uid, ids, context=None):
        for schedule in self.browse(cr, uid, ids, context=context):
            cr.execute('SELECT id \
                FROM hr_schedule \
                WHERE (                                            \
                          (%s >= date_start AND %s <= date_end)    \
                          OR (%s >= date_start and %s <= date_end) \
                      )                                            \
                    AND employee_id=%s \
                    AND id <> %s',(schedule.date_start, schedule.date_start, schedule.date_end, schedule.date_end, schedule.employee_id.id, schedule.id))
            if cr.fetchall():
                return False
        return True


    _constraints = [
        (_schedule_date, 'You cannot have schedules that overlap!', ['date_start','date_end']),
    ]
    
    def get_rest_days_range(self, cr, uid, employee_id, dFrom, dTo, context=None):
        '''Returns a dictionary with the start of each week in the range as key and a
        list of the days of the week that are rest days. Monday is 0.'''
        
        # If the day is in the middle of the week get the start of the week
        if dFrom.weekday() != 0:
            dFrom = (dFrom + relativedelta(days= -dFrom.weekday()))
        if dTo.weekday() != 0:
            dTo = (dTo + relativedelta(days= -dTo.weekday()))

        res = {}
        d = dFrom
        while d <= dTo:
            d_str = d.strftime(OE_DFORMAT)
            res.update({d_str: []})
            ids = self.search(cr, uid, [('employee_id', '=', employee_id),
                                        ('date_start', '<=', d_str),
                                        ('date_end', '>=', d_str)], context=context)
            if len(ids) == 0:
                d += relativedelta(days= +7)
                continue
            elif len(ids) > 1:
                ee_data = self.pool.get('hr.employee').read(cr, uid, employee_id, ['name'],
                                                            context=context)
                raise osv.except_osv(_('Programming Error'),
                                     _('Employee has a scheduled date in more than one schedule. '\
                                       '\nName: %s\nWeek: %s' % (ee_data['name'], d_str)))
            
            res[d_str] = self.get_rest_days_by_id(cr, uid, ids[0], d_str, context=context)
            d += relativedelta(days= +7)
        
        return res
    
    def get_rest_days(self, cr, uid, employee_id, dt, context=None):
        '''If the rest day(s) have been explicitly specified that's what is returned, otherwise
        a guess is returned based on the week days that are not scheduled. If an explicit
        rest day(s) has not been specified an empty list is returned. If it is able to figure
        out the rest days it will return a list of week day integers with Monday being 0.'''
        
        day = dt.strftime(OE_DTFORMAT)
        ids = self.search(cr, uid, [('employee_id', '=', employee_id),
                                    ('date_start', '<=', day),
                                    ('date_end', '>=', day)], context=context)
        if len(ids) == 0:
            return None
        elif len(ids) > 1:
            ee_data = self.pool.get('hr.employee').read(cr, uid, employee_id, ['name'], context=context)
            raise osv.except_osv(_('Programming Error'),
                                 _('Employee has a scheduled date in more than one schedule. '\
                                   '\nName: %s\nDay: %s' % (ee_data['name'], dt.strftime(OE_DFORMAT))))
        
        # If the day is in the middle of the week get the start of the week
        if dt.weekday() == 0:
            week_start = dt.strftime(OE_DFORMAT)
        else:
            week_start = (dt + relativedelta(days= -dt.weekday())).strftime(OE_DFORMAT)
        
        return self.get_rest_days_by_id(cr, uid, ids[0], week_start, context=context)
    
    def get_rest_days_by_id(self, cr, uid, Id, week_start, context=None):
        '''If the rest day(s) have been explicitly specified that's what is returned, otherwise
        a guess is returned based on the week days that are not scheduled. If an explicit
        rest day(s) has not been specified an empty list is returned. If it is able to figure
        out the rest days it will return a list of week day integers with Monday being 0.'''

        res = []

        # Set the boundaries of the week (i.e- start of current week and start of next week)
        #
        sched = self.browse(cr, uid, Id, context=context)
        if not sched.detail_ids:
            return res
        dtFirstDay = datetime.strptime(sched.detail_ids[0].date_start, OE_DTFORMAT)
        date_start = dtFirstDay.strftime(OE_DFORMAT) < week_start and week_start +' '+ dtFirstDay.strftime('%H:%M:%S') or dtFirstDay.strftime(OE_DTFORMAT)
        dtNextWeek = datetime.strptime(date_start, OE_DTFORMAT) + relativedelta(weeks= +1)
        
        # Determine the appropriate rest day list to use
        #
        restday_ids = False
        dSchedStart = datetime.strptime(sched.date_start, OE_DFORMAT).date()
        dWeekStart = datetime.strptime(week_start, OE_DFORMAT).date()
        if dWeekStart == dSchedStart: restday_ids = sched.restday_ids1
        elif dWeekStart == dSchedStart + relativedelta(days= +7): restday_ids = sched.restday_ids2
        elif dWeekStart == dSchedStart + relativedelta(days= +14): restday_ids = sched.restday_ids3
        elif dWeekStart == dSchedStart + relativedelta(days= +21): restday_ids = sched.restday_ids4
        elif dWeekStart == dSchedStart + relativedelta(days= +28): restday_ids = sched.restday_ids5
        
        # If there is explicit rest day data use it, otherwise try to guess based on which
        # days are not scheduled.
        #
        res = []
        if restday_ids:
            res = [rd.sequence for rd in restday_ids]
        else:
            weekdays = ['0','1','2','3','4','5','6']
            scheddays = []
            for dtl in sched.detail_ids:
                # Make sure the date we're examining isn't in the previous week or the next one
                if dtl.date_start < week_start or datetime.strptime(dtl.date_start, OE_DTFORMAT) >= dtNextWeek:
                    continue
                if dtl.dayofweek not in scheddays:
                    scheddays.append(dtl.dayofweek)
            res = [int(d) for d in weekdays if d not in scheddays]
            # If there are no sched.details return nothing instead of *ALL* the days in the week
            if len(res) == 7:
                res = []
        
        return res
    
    def onchange_employee_start_date(self, cr, uid, ids, employee_id, date_start, context=None):
        
        res = {
            'value': {
                'name': ''
            }
        }
        dStart = False
        edata = False
        if employee_id:
            edata = self.pool.get('hr.employee').read(cr, uid, employee_id, ['name', 'contract_id'], context=context)
        if date_start:
            dStart = datetime.strptime(date_start, '%Y-%m-%d').date()
            # The schedule must start on a Monday
            if dStart.weekday() != 0:
                res['value']['date_start'] = False
                res['value']['date_end'] = False
            else:
                dEnd = dStart + relativedelta(days= +6)
                res['value']['date_end'] = dEnd.strftime('%Y-%m-%d')
        
        if edata['name']:
            res['value']['name'] = edata['name']
            if dStart:
                res['value']['name'] = res['value']['name'] +': '+ dStart.strftime('%Y-%m-%d') +' Wk '+ str(dStart.isocalendar()[1])
        
        if edata['contract_id']:
            cdata = self.pool.get('hr.contract').read(cr, uid, edata['contract_id'][0], ['schedule_template_id'], context=context)
            if cdata['schedule_template_id']:
                res['value']['template_id'] = cdata['schedule_template_id']
        
        return res
    
    def delete_details(self, cr, uid, sched_id, context=None):
        
        unlink_ids = []
        schedule = self.browse(cr, uid, sched_id, context=context)
        for detail in schedule.detail_ids:
            unlink_ids.append(detail.id)
        self.pool.get('hr.schedule.detail').unlink(cr, uid, unlink_ids, context=context)
        return
    
    def add_restdays(self, cr, uid, schedule, field_name, rest_days=None, context=None):
        
        restday_ids = []
        if rest_days == None:
            for rd in schedule.template_id.restday_ids:
                restday_ids.append(rd.id)
        else:
            restday_ids = self.pool.get('hr.schedule.weekday').search(cr, uid,
                                                                      [('sequence', 'in', rest_days)],
                                                                      context=context)
        if len(restday_ids) > 0:
            self.write(cr, uid, schedule.id, {field_name: [(6, 0, restday_ids)]}, context=context)

        return

    def create_details(self, cr, uid, sched_id, context=None):
        
        leave_obj = self.pool.get('hr.holidays')
        schedule = self.browse(cr, uid, sched_id, context=context)
        if schedule.template_id:
            
            # Get first day of contract
            dContract = False
            for c in schedule.employee_id.contract_ids:
                d = datetime.strptime(c.date_start, OE_DFORMAT).date()
                if not dContract or d < dContract:
                    dContract = d
            
            leaves = []
            leave_ids = leave_obj.search(cr, uid, [('employee_id', '=', schedule.employee_id.id),
                                                   ('date_from', '<=', schedule.date_end),
                                                   ('date_to', '>=', schedule.date_start),
                                                   ('state', 'in', ['draft', 'validate', 'validate1'])],
                                         context=context)
            for lv in leave_obj.browse(cr, uid, leave_ids, context=context):
                utcdtFrom = utc.localize(datetime.strptime(lv.date_from, OE_DTFORMAT), is_dst=False)
                utcdtTo = utc.localize(datetime.strptime(lv.date_to, OE_DTFORMAT), is_dst=False)
                leaves.append((utcdtFrom, utcdtTo))
            
            user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
            local_tz = timezone(user.tz)
            dCount = datetime.strptime(schedule.date_start, '%Y-%m-%d').date()
            dCountEnd = datetime.strptime(schedule.date_end, '%Y-%m-%d').date()
            dWeekStart = dCount
            dSchedStart = dCount
            while dCount <= dCountEnd:
                
                # Enter the rest day(s)
                #
                if dCount == dSchedStart:
                    self.add_restdays(cr, uid, schedule, 'restday_ids1', context=context)
                elif dCount == dSchedStart + relativedelta(days= +7):
                    self.add_restdays(cr, uid, schedule, 'restday_ids2', context=context)
                elif dCount == dSchedStart + relativedelta(days= +14):
                    self.add_restdays(cr, uid, schedule, 'restday_ids3', context=context)
                elif dCount == dSchedStart + relativedelta(days= +21):
                    self.add_restdays(cr, uid, schedule, 'restday_ids4', context=context)
                elif dCount == dSchedStart + relativedelta(days= +28):
                    self.add_restdays(cr, uid, schedule, 'restday_ids5', context=context)

                utcdtPrevOut = False
                for worktime in schedule.template_id.worktime_ids:
                    
                    hour, sep, minute = worktime.hour_from.partition(':')
                    toHour, toSep, toMin = worktime.hour_to.partition(':')
                    if len(sep) == 0 or len(toSep) == 0:
                        raise osv.except_osv(_('Invalid Time Format'), _('The time should be entered as HH:MM'))
                    
                    # XXX - Someone affected by DST should fix this
                    #
                    dTemp = dWeekStart + relativedelta(days= +(int(worktime.dayofweek)))
                    dtStart = datetime.strptime(dTemp.strftime('%Y-%m-%d') +' '+ hour +':'+ minute +':00', OE_DTFORMAT)
                    locldtStart = local_tz.localize(dtStart, is_dst=False)
                    utcdtStart = locldtStart.astimezone(utc)
                    dDay = utcdtStart.astimezone(local_tz).date()
                    
                    dtEnd = datetime.strptime(dTemp.strftime('%Y-%m-%d') +' '+ toHour +':'+ toMin +':00', OE_DTFORMAT)
                    locldtEnd = local_tz.localize(dtEnd, is_dst=False)
                    utcdtEnd = locldtEnd.astimezone(utc)
                    if utcdtEnd < utcdtStart:
                        utcdtEnd += relativedelta(days= +1)
                    
                    # If this record appears to be before the previous record it means the
                    # shift continues into the next day
                    if utcdtPrevOut and utcdtStart < utcdtPrevOut:
                        utcdtStart += relativedelta(days= +1)
                        utcdtEnd += relativedelta(days= +1)
                    
                    # Skip days before start of contract
                    _d_str = utcdtStart.astimezone(local_tz).strftime(OE_DFORMAT)
                    _d = datetime.strptime(_d_str, OE_DFORMAT).date()
                    if dContract > _d:
                        continue
                    
                    # Leave empty holes where there are leaves
                    #
                    _skip = False
                    for utcdtFrom, utcdtTo in leaves:
                        if utcdtFrom <= utcdtStart and utcdtTo >= utcdtEnd:
                            _skip = True
                            break
                        elif utcdtFrom > utcdtStart and utcdtFrom <= utcdtEnd:
                            if utcdtTo == utcdtEnd:
                                _skip = True
                            else:
                                utcdtEnd = utcdtFrom + timedelta(seconds= -1)
                            break
                        elif utcdtTo >= utcdtStart and utcdtTo < utcdtEnd:
                            if utcdtTo == utcdtEnd:
                                _skip = True
                            else:
                                utcdtStart = utcdtTo + timedelta(seconds= +1)
                            break
                    
                    # Do not recreate details that have not been deleted because
                    # they are locked.
                    #
                    for detail in schedule.detail_ids:
                        if detail.day == dDay.strftime(OE_DFORMAT) and              \
                          utcdtStart.strftime(OE_DTFORMAT) >= detail.date_start and \
                          utcdtStart.strftime(OE_DTFORMAT) <= detail.date_end:
                            _skip = True
                            break
                    
                    if not _skip:
                        val = {
                            'name': schedule.name,
                            'dayofweek': worktime.dayofweek,
                            'day': dDay,
                            'date_start': utcdtStart.strftime('%Y-%m-%d %H:%M:%S'),
                            'date_end': utcdtEnd.strftime('%Y-%m-%d %H:%M:%S'),
                            'schedule_id': sched_id,
                        }
                        self.write(cr, uid, sched_id, {'detail_ids': [(0, 0, val)]}, context=context)
                    
                    utcdtPrevOut = utcdtEnd
                
                dCount = dWeekStart + relativedelta(weeks= +1)
                dWeekStart = dCount
        return True
    
    def create(self, cr, uid, vals, context=None):
        
        my_id = super(hr_schedule, self).create(cr, uid, vals, context=context)
        
        self.create_details(cr, uid, my_id, context=context)
            
        return my_id
    
    def create_mass_schedule(self, cr, uid, context=None):
        '''Creates tentative schedules for all employees based on the
        schedule template attached to their contract. Called from the scheduler.'''
        
        sched_obj = self.pool.get('hr.schedule')
        ee_obj = self.pool.get('hr.employee')
        
        # Create a two-week schedule beginning from Monday of next week.
        #
        dt = datetime.today()
        days = 7 - dt.weekday()
        dt += relativedelta(days= +days)
        dStart = dt.date()
        dEnd = dStart + relativedelta(weeks= +2, days= -1)
        
        # Create schedules for each employee in each department
        #
        dept_ids = self.pool.get('hr.department').search(cr, uid, [],
                                                         context=context)
        for dept in self.pool.get('hr.department').browse(cr, uid, dept_ids, context=context):
            ee_ids = ee_obj.search(cr, uid, [
                                             ('department_id', '=', dept.id),
                                            ], order="name", context=context)
            if len(ee_ids) == 0:
                continue
            
            for ee in ee_obj.browse(cr, uid, ee_ids, context=context):
                
                if not ee.contract_id or not ee.contract_id.schedule_template_id:
                    continue
                
                # If there are overlapping schedules, don't create
                #
                overlap_sched_ids = sched_obj.search(cr, uid, [('employee_id', '=', ee.id),
                                                       ('date_start', '<=', dEnd.strftime('%Y-%m-%d')),
                                                       ('date_end', '>=', dStart.strftime('%Y-%m-%d'))],
                                             context=context)
                if len(overlap_sched_ids) > 0:
                    continue
                
                sched = {
                    'name': ee.name +': '+ dStart.strftime('%Y-%m-%d') +' Wk '+ str(dStart.isocalendar()[1]),
                    'employee_id': ee.id,
                    'template_id': ee.contract_id.schedule_template_id.id,
                    'date_start': dStart.strftime('%Y-%m-%d'),
                    'date_end': dEnd.strftime('%Y-%m-%d'),
                }
                sched_obj.create(cr, uid, sched, context=context)
    
    def deletable(self, cr, uid, sched_id, context=None):
        
        sched = self.browse(cr, uid, sched_id, context=context)
        if sched.state not in ['draft', 'unlocked']:
            return False
        for detail in sched.detail_ids:
            if detail.state not in ['draft', 'unlocked']:
                return False
        
        return True
    
    def unlink(self, cr, uid, ids, context=None):
        
        detail_obj = self.pool.get('hr.schedule.detail')
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        schedule_ids = []
        for schedule in self.browse(cr, uid, ids, context=context):
            # Do not remove schedules that are not in draft or unlocked state
            if not self.deletable(cr, uid, schedule.id, context):
                continue
            
            # Delete the schedule details associated with this schedule
            #
            detail_ids = []
            [detail_ids.append(detail.id) for detail in schedule.detail_ids]
            if len(detail_ids) > 0:
                detail_obj.unlink(cr, uid, detail_ids, context=context)
            
            schedule_ids.append(schedule.id)
            
        return super(hr_schedule, self).unlink(cr, uid, schedule_ids, context=context)
    
    def _workflow_common(self, cr, uid, ids, signal, next_state, context=None):
        
        wkf = netsvc.LocalService('workflow')
        for sched in self.browse(cr, uid, ids, context=context):
            for detail in sched.detail_ids:
                wkf.trg_validate(uid, 'hr.schedule.detail', detail.id, signal, cr)
            self.write(cr, uid, sched.id, {'state': next_state}, context=context)
        return True
    
    def workflow_validate(self, cr, uid, ids, context=None):
        
        return self._workflow_common(cr, uid, ids, 'signal_validate', 'validate', context=context)
    
    def details_locked(self, cr, uid, ids, context=None):
        
        for sched in self.browse(cr, uid, ids, context=context):
            for detail in sched.detail_ids:
                if detail.state != 'locked':
                    return False
        
        return True
    
    def workflow_lock(self, cr, uid, ids, context=None):
        '''Lock the Schedule Record. Expects to be called by its schedule detail
        records as they are locked one by one.  When the last one has been locked
        the schedule will also be locked.'''
        
        all_locked = True
        for sched in self.browse(cr, uid, ids, context=context):
            if self.details_locked(cr, uid, [sched.id], context):
                self.write(cr, uid, sched.id, {'state': 'locked'}, context=context)
            else:
                all_locked = False
        
        return all_locked
    
    def workflow_unlock(self, cr, uid, ids, context=None):
        '''Unlock the Schedule Record. Expects to be called by its schedule detail
        records as they are unlocked one by one.  When the first one has been unlocked
        the schedule will also be unlocked.'''
        
        all_locked = True
        for sched in self.browse(cr, uid, ids, context=context):
            if not self.details_locked(cr, uid, [sched.id], context):
                self.write(cr, uid, sched.id, {'state': 'unlocked'}, context=context)
            else:
                all_locked = False
        
        return all_locked == False

class schedule_detail(osv.osv):
    _name = "hr.schedule.detail"
    _description = "Schedule Detail"

    def _day_compute(self, cr, uid, ids, field_name, args, context=None):
        res = dict.fromkeys(ids, '')
        for obj in self.browse(cr, uid, ids, context=context):
            res[obj.id] = time.strftime('%Y-%m-%d', time.strptime(obj.date_start, '%Y-%m-%d %H:%M:%S'))
        return res

    def _get_ids_from_sched(self, cr, uid, ids, context=None):
        res = []
        for sched in self.pool.get('hr.schedule').browse(cr, uid, ids, context=context):
            for detail in sched.detail_ids:
                res.append(detail.id)
        return res
    
    _columns = {
        'name' : fields.char("Name", size=64, required=True),
        'dayofweek': fields.selection(DAYOFWEEK_SELECTION, 'Day of Week', required=True, select=True),
        'date_start' : fields.datetime('Start Date and Time', required=True),
        'date_end' : fields.datetime('End Date and Time', required=True),
        'day' : fields.date('Day', required=True, select=1),
        'schedule_id': fields.many2one('hr.schedule', 'Schedule', required=True),
        'department_id': fields.related('schedule_id', 'department_id', type='many2one',
                                        relation='hr.department', string='Department', store=True),
        'employee_id': fields.related('schedule_id', 'employee_id', type='many2one',
                                      relation='hr.employee', string='Employee', store=True),
        'alert_ids': fields.one2many('hr.schedule.alert', 'sched_detail_id', 'Alerts', readonly=True),
        'state': fields.selection((
                                   ('draft', 'Draft'), ('validate', 'Confirmed'),
                                   ('locked', 'Locked'), ('unlocked', 'Unlocked'),
                                  ), 'State', required=True, readonly=True),
    }

    _order = 'schedule_id, date_start, dayofweek'

    _defaults = {
        'dayofweek' : '0',
        'state': 'draft',
    }
    
    def _detail_date(self, cr, uid, ids, context=None):
        for detail in self.browse(cr, uid, ids, context=context):
            cr.execute('SELECT id \
                FROM hr_schedule_detail \
                WHERE (date_start <= %s and %s <= date_end) \
                    AND schedule_id=%s \
                    AND id <> %s',(detail.date_end, detail.date_start, detail.schedule_id.id, detail.id))
            if cr.fetchall():
                return False
        return True


    _constraints = [
        (_detail_date, 'You cannot have scheduled days that overlap!', ['date_start','date_end']),
    ]
    
    def scheduled_hours_on_day(self, cr, uid, employee_id, contract_id, dt, context=None):
        
        dtDelta = timedelta(seconds=0)
        shifts = self.scheduled_begin_end_times(cr, uid, employee_id,
                                                contract_id, dt, context=context)
        for start, end in shifts:
            dtDelta += end - start
        
        return float(dtDelta.seconds / 60) / 60.0
    
    def scheduled_begin_end_times(self, cr, uid, employee_id, contract_id, dt, context=None):
        '''Returns a list of tuples containing shift start and end times for the day'''
        
        res = []
        detail_ids = self.search(cr, uid, [
                                          ('schedule_id.employee_id.id', '=', employee_id),
                                          ('day', '=', dt.strftime('%Y-%m-%d')),
                                         ],
                                order='date_start',
                                context=context)
        if len(detail_ids) > 0:
            sched_details = self.browse(cr, uid, detail_ids, context=context)
            for detail in sched_details:
                res.append((
                            datetime.strptime(detail.date_start, '%Y-%m-%d %H:%M:%S'),
                            datetime.strptime(detail.date_end, '%Y-%m-%d %H:%M:%S'),
                            ))
        
        return res
    
    def scheduled_hours_on_day_from_range(self, d, range_dict):
        
        dtDelta = timedelta(seconds=0)
        shifts = range_dict[d.strftime(OE_DFORMAT)]
        for start, end in shifts:
            dtDelta += end - start
        
        return float(dtDelta.seconds / 60) / 60.0
    
    def scheduled_begin_end_times_range(self, cr, uid, employee_id, contract_id,
                                        dStart, dEnd, context=None):
        '''Returns a dictionary with the dates in range dtStart - dtEnd as keys and
        a list of tuples containing shift start and end times during those days as values'''
        
        res = {}
        d = dStart
        while d <= dEnd:
            res.update({d.strftime(OE_DFORMAT): []})
            d += timedelta(days= +1)
        
        detail_ids = self.search(cr, uid, [
                                          ('schedule_id.employee_id.id', '=', employee_id),
                                          ('day', '>=', dStart.strftime('%Y-%m-%d')),
                                          ('day', '<=', dEnd.strftime('%Y-%m-%d')),
                                         ],
                                order='date_start',
                                context=context)
        if len(detail_ids) > 0:
            sched_details = self.browse(cr, uid, detail_ids, context=context)
            for detail in sched_details:
                res[detail.day].append((
                                        datetime.strptime(detail.date_start, '%Y-%m-%d %H:%M:%S'),
                                        datetime.strptime(detail.date_end, '%Y-%m-%d %H:%M:%S'),
                                      ))
        
        return res
    
    def _remove_direct_alerts(self, cr, uid, ids, context=None):
        '''Remove alerts directly attached to the schedule detail and return a unique
        list of tuples of employee id and schedule detail date.'''
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        alert_obj = self.pool.get('hr.schedule.alert')
        
        # Remove alerts directly attached to these schedule details
        #
        alert_ids = []
        scheds = []
        sched_keys = []
        for sched_detail in self.browse(cr, uid, ids, context=context):
            
            [alert_ids.append(alert.id) for alert in sched_detail.alert_ids]
            
            # Hmm, creation of this record triggers a workflow action that tries to
            # write to it. But it seems that computed fields aren't available at
            # this stage. So, use a fallback and compute the day ourselves.
            day = sched_detail.day
            if not sched_detail.day:
                day = time.strftime('%Y-%m-%d', time.strptime(sched_detail.date_start, '%Y-%m-%d %H:%M:%S'))            
            key = str(sched_detail.schedule_id.employee_id.id) + day
            if key not in sched_keys:
                scheds.append((sched_detail.schedule_id.employee_id.id, day))
                sched_keys.append(key)
        
        if len(alert_ids) > 0: alert_obj.unlink(cr, uid, alert_ids, context=context)
        
        return scheds
    
    def _recompute_alerts(self, cr, uid, attendances, context=None):
        '''Recompute alerts for each record in schedule detail.'''
        
        alert_obj = self.pool.get('hr.schedule.alert')
        
        # Remove all alerts for the employee(s) for the day and recompute.
        #
        for ee_id, strDay in attendances:
            
            # Today's records will be checked tomorrow. Future records can't generate alerts.
            if strDay >= fields.date.context_today(self, cr, uid, context=context):
                continue
            
            # XXX - Someone who cares about DST should fix this
            #
            data = self.pool.get('res.users').read(cr, uid, uid, ['tz'], context=context)
            dt = datetime.strptime(strDay + ' 00:00:00', '%Y-%m-%d %H:%M:%S')
            lcldt = timezone(data['tz']).localize(dt, is_dst=False)
            utcdt = lcldt.astimezone(utc)
            utcdtNextDay = utcdt + relativedelta(days= +1)
            strDayStart = utcdt.strftime('%Y-%m-%d %H:%M:%S')
            strNextDay = utcdtNextDay.strftime('%Y-%m-%d %H:%M:%S')
            
            alert_ids = alert_obj.search(cr, uid, [('employee_id', '=', ee_id),
                                                    '&', ('name', '>=', strDayStart),
                                                         ('name', '<', strNextDay)],
                                         context=context)
            alert_obj.unlink(cr, uid, alert_ids, context=context)
            alert_obj.compute_alerts_by_employee(cr, uid, ee_id, strDay, context=context)
    
    def create(self, cr, uid, vals, context=None):
        
        if 'day' not in vals and 'date_start' in vals:
            # XXX - Someone affected by DST should fix this
            #
            user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
            local_tz = timezone(user.tz)
            dtStart = datetime.strptime(vals['date_start'], OE_DTFORMAT)
            locldtStart = local_tz.localize(dtStart, is_dst=False)
            utcdtStart = locldtStart.astimezone(utc)
            dDay = utcdtStart.astimezone(local_tz).date()
            vals.update({'day': dDay})
        
        res = super(schedule_detail, self).create(cr, uid, vals, context=context)
        
        obj = self.browse(cr, uid, res, context=context)
        attendances = [(obj.schedule_id.employee_id.id, fields.date.context_today(self, cr, uid, context=context))]
        self._recompute_alerts(cr, uid, attendances, context=context)
        
        return res
    
    def unlink(self, cr, uid, ids, context=None):
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        detail_ids = []
        for detail in self.browse(cr, uid, ids, context=context):
            if detail.state in ['draft', 'unlocked']:
                detail_ids.append(detail.id)
        
        # Remove alerts directly attached to the schedule details
        #
        attendances = self._remove_direct_alerts(cr, uid, detail_ids, context=context)
        
        res = super(schedule_detail, self).unlink(cr, uid, detail_ids, context=context)
        
        # Remove all alerts for the employee(s) for the day and recompute.
        #
        self._recompute_alerts(cr, uid, attendances, context=context)
        
        return res
    
    def write(self, cr, uid, ids, vals, context=None):
        
        # Flag for checking wether we have to recompute alerts
        trigger_alert = False
        for k, v in vals.iteritems():
            if k in ['date_start', 'date_end']:
                trigger_alert = True
        
        if trigger_alert:
            # Remove alerts directly attached to the attendances
            #
            attendances = self._remove_direct_alerts(cr, uid, ids, context=context)
        
        res = super(schedule_detail, self).write(cr, uid, ids, vals, context=context)
        
        if trigger_alert:
            # Remove all alerts for the employee(s) for the day and recompute.
            #
            self._recompute_alerts(cr, uid, attendances, context=context)
        
        return res
    
    def workflow_lock(self, cr, uid, ids, context=None):
        
        wkf = netsvc.LocalService('workflow')
        for detail in self.browse(cr, uid, ids, context=context):
            self.write(cr, uid, [detail.id], {'state': 'locked'}, context=context)
            wkf.trg_validate(uid, 'hr.schedule', detail.schedule_id.id, 'signal_lock', cr)
        
        return True
    
    def workflow_unlock(self, cr, uid, ids, context=None):
        
        wkf = netsvc.LocalService('workflow')
        for detail in self.browse(cr, uid, ids, context=context):
            self.write(cr, uid, [detail.id], {'state': 'unlocked'}, context=context)
            wkf.trg_validate(uid, 'hr.schedule', detail.schedule_id.id, 'signal_unlock', cr)
        
        return True

class hr_schedule_request(osv.osv):
    
    _name = 'hr.schedule.request'
    _description = 'Change Request'
    
    _inherit = ['mail.thread']
    
    _columns = {
        'employee_id': fields.many2one('hr.employee', 'Employee', required=True),
        'date': fields.date('Date', required=True),
        'type': fields.selection((
                                  ('missedp', 'Missed Punch'),
                                  ('adjp', 'Punch Adjustment'),
                                  ('absence', 'Absence'),
                                  ('schedadj', 'Schedule Adjustment'),
                                  ('other', 'Other'),
                                 ), 'Type', required=True),
        'message': fields.text('Message'),
        'state': fields.selection((
                                   ('pending', 'Pending'),
                                   ('auth', 'Authorized'),
                                   ('denied', 'Denied'),
                                   ('cancel', 'Cancelled'),
                                  ), 'State', required=True, readonly=True),
    }
    
    _defaults = {
        'state': 'pending',
    }

class hr_schedule_alert(osv.osv):
    
    _name = 'hr.schedule.alert'
    _description = 'Attendance Exception'
    
    _inherit = ['mail.thread', 'resource.calendar']
    
    def _get_employee_id(self, cr, uid, ids, field_name, arg, context=None):
        
        res = {}
        for alert in self.browse(cr, uid, ids, context=context):
            if alert.punch_id:
                res[alert.id] = alert.punch_id.employee_id.id
            elif alert.sched_detail_id:
                res[alert.id] = alert.sched_detail_id.schedule_id.employee_id.id
            else:
                res[alert.id] = False
        
        return res
    
    _columns = {
        'name': fields.datetime('Date and Time', required=True, readonly=True),
        'rule_id': fields.many2one('hr.schedule.alert.rule', 'Alert Rule', required=True, readonly=True),
        'punch_id': fields.many2one('hr.attendance', 'Triggering Punch', readonly=True),
        'sched_detail_id': fields.many2one('hr.schedule.detail', 'Schedule Detail', readonly=True),
        'employee_id': fields.function(_get_employee_id, type='many2one', obj='hr.employee',
                                       method=True, store=True, string='Employee', readonly=True),
        'department_id': fields.related('employee_id', 'department_id', type='many2one', store=True,
                                        relation='hr.department', string='Department', readonly=True),
        'severity': fields.related('rule_id', 'severity', type='char', string='Severity',
                                   store=True, readonly=True),
        'state': fields.selection((
                                   ('unresolved', 'Unresolved'),
                                   ('resolved', 'Resolved'),
                                  ), 'State', readonly=True),
    }
    
    _defaults = {
        'state': 'unresolved',
    }
    
    _sql_constraints = [('all_unique', 'UNIQUE(punch_id,sched_detail_id,name,rule_id)', 'Duplicate Record!')]
    
    _track = {
        'state': {
            'hr_schedule.mt_alert_resolved': lambda self, cr,uid, obj, ctx=None: obj['state'] == 'resolved',
            'hr_schedule.mt_alert_unresolved': lambda self, cr,uid, obj, ctx=None: obj['state'] == 'unresolved',
        },
    }
    
    def check_for_alerts(self, cr, uid, context=None):
        '''Check the schedule detail and attendance records for yesterday
        against the scheduling/attendance alert rules. If any rules match create a 
        record in the database.'''
        
        dept_obj = self.pool.get('hr.department')
        detail_obj = self.pool.get('hr.schedule.detail')
        attendance_obj = self.pool.get('hr.attendance')
        rule_obj = self.pool.get('hr.schedule.alert.rule')
        
        # XXX - Someone who cares about DST should fix ths
        #
        data = self.pool.get('res.users').read(cr, uid, uid, ['tz'], context=context)
        dtToday = datetime.strptime(datetime.now().strftime('%Y-%m-%d') + ' 00:00:00', '%Y-%m-%d %H:%M:%S')
        lcldtToday = timezone(data['tz'] and data['tz'] or 'UTC').localize(dtToday, is_dst=False)
        utcdtToday = lcldtToday.astimezone(utc)
        utcdtYesterday = utcdtToday + relativedelta(days= -1)
        strToday = utcdtToday.strftime('%Y-%m-%d %H:%M:%S')
        strYesterday = utcdtYesterday.strftime('%Y-%m-%d %H:%M:%S')
        
        dept_ids = dept_obj.search(cr, uid, [], context=context)
        for dept in dept_obj.browse(cr, uid, dept_ids, context=context):
            for employee in dept.member_ids:
                
                # Get schedule and attendance records for the employee for the day
                #
                sched_detail_ids = detail_obj.search(cr, uid,[('schedule_id.employee_id', '=', employee.id),
                                                              '&',
                                                                 ('date_start', '>=', strYesterday),
                                                                 ('date_start', '<', strToday),
                                                             ],
                                                     order='date_start',
                                                     context=context)
                attendance_ids = attendance_obj.search(cr, uid, [('employee_id', '=', employee.id),
                                                              '&',
                                                                 ('name', '>=', strYesterday),
                                                                 ('name', '<', strToday),
                                                             ],
                                                       order='name',
                                                       context=context)
                
                # Run the schedule and attendance records against each active rule, and
                # create alerts for each result returned.
                #
                rule_ids = rule_obj.search(cr, uid, [('active', '=', True)], context=context)
                for rule in rule_obj.browse(cr, uid, rule_ids, context=context):
                    res = rule_obj.check_rule(cr, uid, rule,
                                              detail_obj.browse(cr, uid, sched_detail_ids, context=context),
                                              attendance_obj.browse(cr, uid, attendance_ids, context=context),
                                              context=context)
                    
                    for strdt, attendance_id in res['punches']:
                        # skip if it has already been triggered
                        ids = self.search(cr, uid, [('punch_id','=',attendance_id),
                                                    ('rule_id','=',rule.id),
                                                    ('name','=',strdt),
                                                   ],
                                          context=context)
                        if len(ids) > 0:
                            continue
                        
                        self.create(cr, uid, {'name': strdt,
                                              'rule_id': rule.id,
                                              'punch_id': attendance_id},
                                         context=context)
                    
                    for strdt, detail_id in res['schedule_details']:
                        # skip if it has already been triggered
                        ids = self.search(cr, uid, [('sched_detail_id','=',detail_id),
                                                    ('rule_id','=',rule.id),
                                                    ('name','=',strdt),
                                                   ],
                                          context=context)
                        if len(ids) > 0:
                            continue
                        
                        self.create(cr, uid, {'name': strdt,
                                              'rule_id': rule.id,
                                              'sched_detail_id': detail_id},
                                         context=context)
    
    def _get_normalized_attendance(self, cr, uid, employee_id, utcdt, att_ids, context=None):
        
        att_obj = self.pool.get('hr.attendance')
        attendances = att_obj.browse(cr, uid, att_ids, context=context)
        strToday = utcdt.strftime(OE_DTFORMAT)
        
        # If the first punch is a punch-out then get the corresponding punch-in
        # from the previous day.
        #
        if len(attendances) > 0 and attendances[0].action != 'sign_in':
            strYesterday = (utcdt - timedelta(days=1)).strftime(OE_DTFORMAT)
            ids = att_obj.search(cr, uid, [('employee_id', '=', employee_id),
                                            '&', ('name', '>=', strYesterday),
                                                 ('name', '<', strToday),
                                          ],
                                 order='name', context=context)
            att2 = att_obj.browse(cr, uid, ids, context=context)
            if len(att2) > 0 and att2[-1].action == 'sign_in':
                att_ids = [att2[-1].id] + att_ids
            else:
                att_ids = att_ids[1:]
        
        # If the last punch is a punch-in then get the corresponding punch-out
        # from the next day.
        #
        if len(attendances) > 0 and attendances[-1].action != 'sign_out':
            strTommorow = (utcdt + timedelta(days=1)).strftime(OE_DTFORMAT)
            ids = att_obj.search(cr, uid, [('employee_id', '=', employee_id),
                                            '&', ('name', '>=', strToday),
                                                 ('name', '<', strTommorow),
                                          ],
                                 order='name', context=context)
            att2 = att_obj.browse(cr, uid, ids, context=context)
            if len(att2) > 0 and att2[0].action == 'sign_out':
                att_ids = att_ids + [att2[0].id]
            else:
                att_ids = att_ids[:-1]
        
        return att_ids
    
    def compute_alerts_by_employee(self, cr, uid, employee_id, strDay, context=None):
        '''Compute alerts for employee on specified day.'''
        
        detail_obj = self.pool.get('hr.schedule.detail')
        attendance_obj = self.pool.get('hr.attendance')
        rule_obj = self.pool.get('hr.schedule.alert.rule')
        
        # XXX - Someone who cares about DST should fix ths
        #
        data = self.pool.get('res.users').read(cr, uid, uid, ['tz'], context=context)
        dt = datetime.strptime(strDay + ' 00:00:00', '%Y-%m-%d %H:%M:%S')
        lcldt = timezone(data['tz']).localize(dt, is_dst=False)
        utcdt = lcldt.astimezone(utc)
        utcdtNextDay = utcdt + relativedelta(days= +1)
        strToday = utcdt.strftime('%Y-%m-%d %H:%M:%S')
        strNextDay = utcdtNextDay.strftime('%Y-%m-%d %H:%M:%S')
        
        # Get schedule and attendance records for the employee for the day
        #
        sched_detail_ids = detail_obj.search(cr, uid,[('schedule_id.employee_id', '=', employee_id),
                                                      '&',
                                                         ('day', '>=', strToday),
                                                         ('day', '<', strNextDay),
                                                     ],
                                             order='date_start',
                                             context=context)
        attendance_ids = attendance_obj.search(cr, uid, [('employee_id', '=', employee_id),
                                                      '&',
                                                         ('name', '>=', strToday),
                                                         ('name', '<', strNextDay),
                                                     ],
                                               order='name',
                                               context=context)
        attendance_ids = self._get_normalized_attendance(cr, uid, employee_id, utcdt,
                                                         attendance_ids, context)
        
        # Run the schedule and attendance records against each active rule, and
        # create alerts for each result returned.
        #
        rule_ids = rule_obj.search(cr, uid, [('active', '=', True)], context=context)
        for rule in rule_obj.browse(cr, uid, rule_ids, context=context):
            res = rule_obj.check_rule(cr, uid, rule,
                                      detail_obj.browse(cr, uid, sched_detail_ids, context=context),
                                      attendance_obj.browse(cr, uid, attendance_ids, context=context),
                                      context=context)
            
            for strdt, attendance_id in res['punches']:
                # skip if it has already been triggered
                ids = self.search(cr, uid, [('punch_id','=',attendance_id),
                                            ('rule_id','=',rule.id),
                                            ('name','=',strdt),
                                           ],
                                  context=context)
                if len(ids) > 0:
                    continue
                
                self.create(cr, uid, {'name': strdt,
                                      'rule_id': rule.id,
                                      'punch_id': attendance_id},
                                 context=context)
            
            for strdt, detail_id in res['schedule_details']:
                # skip if it has already been triggered
                ids = self.search(cr, uid, [('sched_detail_id','=',detail_id),
                                            ('rule_id','=',rule.id),
                                            ('name','=',strdt),
                                           ],
                                  context=context)
                if len(ids) > 0:
                    continue
                
                self.create(cr, uid, {'name': strdt,
                                      'rule_id': rule.id,
                                      'sched_detail_id': detail_id},
                                 context=context)

class hr_schedule_alert_rule(osv.osv):
    
    _name = 'hr.schedule.alert.rule'
    _description = 'Scheduling/Attendance Exception Rule'
    
    _columns = {
        'name': fields.char('Name', size=64, required=True),
        'code': fields.char('Code', size=10, required=True),
        'severity': fields.selection((
                                      ('low', 'Low'),
                                      ('medium', 'Medium'),
                                      ('high', 'High'),
                                      ('critical', 'Critical'),
                                     ), 'Severity', required=True),
        'grace_period': fields.integer('Grace Period', help='In the case of early or late rules, the amount of time before/after the scheduled time that the rule will trigger.'),
        'window': fields.integer('Window of Activation'),
        'active': fields.boolean('Active'),
    }
    
    _defaults = {
        'active': True,
        'severity': 'low',
    }
    
    def check_rule(self, cr, uid, rule, sched_details, punches, context=None):
        '''Identify if the schedule detail or attendance records trigger any rule. If
        they do return the datetime and id of the record that triggered it in one of
        the appropriate lists.  All schedule detail and attendance records are expected
        to be in sorted order according to datetime.'''
        
        res = {'schedule_details': [], 'punches': []}
        
        if rule.code == 'MISSPUNCH':
            prev = False
            for punch in punches:
                if not prev:
                    prev = punch
                    if punch.action != 'sign_in':
                        res['punches'].append((punch.name, punch.id))
                elif prev.action == 'sign_in':
                    if punch.action != 'sign_out':
                        res['punches'].append((punch.name, punch.id))
                elif prev.action == 'sign_out':
                    if punch.action != 'sign_in':
                        res['punches'].append((punch.name, punch.id))
                prev = punch
            if len(punches) > 0 and prev.action != 'sign_out':
                res['punches'].append((punch.name, punch.id))
        elif rule.code == 'UNSCHEDATT':
            for punch in punches:
                if punch.action == 'sign_in':
                    isMatch = False
                    dtPunch = datetime.strptime(punch.name, '%Y-%m-%d %H:%M:%S')
                    for detail in sched_details:
                        dtSched = datetime.strptime(detail.date_start, '%Y-%m-%d %H:%M:%S')
                        difference = 0
                        if dtSched >= dtPunch:
                            difference = abs((dtSched - dtPunch).seconds) / 60
                        else:
                            difference = abs((dtPunch - dtSched).seconds) / 60
                        if difference < rule.window:
                            isMatch = True
                            break
                    if not isMatch:
                        res['punches'].append((punch.name, punch.id))
        elif rule.code == 'MISSATT':
            if len(sched_details) > len(punches):
                for detail in sched_details:
                    isMatch = False
                    dtSched = datetime.strptime(detail.date_start, '%Y-%m-%d %H:%M:%S')
                    for punch in punches:
                        if punch.action == 'sign_in':
                            dtPunch = datetime.strptime(punch.name, '%Y-%m-%d %H:%M:%S')
                            difference = 0
                            if dtSched >= dtPunch:
                                difference = (dtSched - dtPunch).seconds / 60
                            else:
                                difference = (dtPunch - dtSched).seconds / 60
                            if difference < rule.window:
                                isMatch = True
                                break
                    if not isMatch:
                        res['schedule_details'].append((detail.date_start, detail.id))
        elif rule.code == 'UNSCHEDOT':
            actual_hours = 0
            sched_hours = 0
            for detail in sched_details:
                dtStart = datetime.strptime(detail.date_start, '%Y-%m-%d %H:%M:%S')
                dtEnd = datetime.strptime(detail.date_end, '%Y-%m-%d %H:%M:%S')
                sched_hours += float((dtEnd - dtStart).seconds / 60) / 60.0
            
            dtStart = False
            for punch in punches:
                if punch.action == 'sign_in':
                    dtStart = datetime.strptime(punch.name, '%Y-%m-%d %H:%M:%S')
                elif punch.action == 'sign_out':
                    dtEnd = datetime.strptime(punch.name, '%Y-%m-%d %H:%M:%S')
                    actual_hours += float((dtEnd - dtStart).seconds / 60) / 60.0
                    if actual_hours > 8 and sched_hours <= 8:
                        res['punches'].append((punch.name, punch.id))
        elif rule.code == 'TARDY':
            for detail in sched_details:
                isMatch = False
                dtSched = datetime.strptime(detail.date_start, '%Y-%m-%d %H:%M:%S')
                for punch in punches:
                    if punch.action == 'sign_in':
                        dtPunch = datetime.strptime(punch.name, '%Y-%m-%d %H:%M:%S')
                        difference = 0
                        if dtPunch > dtSched:
                            difference = (dtPunch - dtSched).seconds / 60
                        if difference < rule.window and difference > rule.grace_period:
                            isMatch = True
                            break
                if isMatch:
                    res['punches'].append((punch.name, punch.id))
        elif rule.code == 'LVEARLY':
            for detail in sched_details:
                isMatch = False
                dtSched = datetime.strptime(detail.date_end, '%Y-%m-%d %H:%M:%S')
                for punch in punches:
                    if punch.action == 'sign_out':
                        dtPunch = datetime.strptime(punch.name, '%Y-%m-%d %H:%M:%S')
                        difference = 0
                        if dtPunch < dtSched:
                            difference = (dtSched - dtPunch).seconds / 60
                        if difference < rule.window and difference > rule.grace_period:
                            isMatch = True
                            break
                if isMatch:
                    res['punches'].append((punch.name, punch.id))
        elif rule.code == 'INEARLY':
            for detail in sched_details:
                isMatch = False
                dtSched = datetime.strptime(detail.date_start, '%Y-%m-%d %H:%M:%S')
                for punch in punches:
                    if punch.action == 'sign_in':
                        dtPunch = datetime.strptime(punch.name, '%Y-%m-%d %H:%M:%S')
                        difference = 0
                        if dtPunch < dtSched:
                            difference = (dtSched - dtPunch).seconds / 60
                        if difference < rule.window and difference > rule.grace_period:
                            isMatch = True
                            break
                if isMatch:
                    res['punches'].append((punch.name, punch.id))
        elif rule.code == 'OUTLATE':
            for detail in sched_details:
                isMatch = False
                dtSched = datetime.strptime(detail.date_end, '%Y-%m-%d %H:%M:%S')
                for punch in punches:
                    if punch.action == 'sign_out':
                        dtPunch = datetime.strptime(punch.name, '%Y-%m-%d %H:%M:%S')
                        difference = 0
                        if dtPunch > dtSched:
                            difference = (dtPunch - dtSched).seconds / 60
                        if difference < rule.window and difference > rule.grace_period:
                            isMatch = True
                            break
                if isMatch:
                    res['punches'].append((punch.name, punch.id))
        elif rule.code == 'OVRLP':
            leave_obj = self.pool.get('hr.holidays')
            for punch in punches:
                if punch.action == 'sign_in':
                    dtStart = datetime.strptime(punch.name, '%Y-%m-%d %H:%M:%S')
                elif punch.action == 'sign_out':
                    dtEnd = datetime.strptime(punch.name, '%Y-%m-%d %H:%M:%S')
                    leave_ids = leave_obj.search(cr, uid, [('employee_id', '=', punch.employee_id.id),
                                                           ('type', '=', 'remove'),
                                                           ('date_from', '<=', dtEnd.strftime(OE_DTFORMAT)),
                                                           ('date_to', '>=', dtStart.strftime(OE_DTFORMAT)),
                                                           ('state', 'in', ['validate', 'validate1'])],
                                                 context=context)
                    if len(leave_ids) > 0:
                        res['punches'].append((punch.name, punch.id))
                        break
        
        return res

class hr_schedule_template(osv.osv):
    
    _name = 'hr.schedule.template'
    _description = 'Employee Working Schedule Template'
    
    def _get_var_list(self, cr, uid, context=None):
        
        return [('decr', 'Decreasing')]
    
    _columns = {
        'name' : fields.char("Name", size=64, required=True),
        'company_id' : fields.many2one('res.company', 'Company', required=False),
        'worktime_ids' : fields.one2many('hr.schedule.template.worktime', 'template_id', 'Working Time'),
        'restday_ids': fields.many2many('hr.schedule.weekday', 'schedule_template_restdays_rel', 'sched_id',
                                        'weekday_id', string='Rest Days'),
        'variable_restday': fields.boolean('Variable Rest Day'),
        'variable_type': fields.selection(_get_var_list, 'Variable Rest Day Type'),
    }
    
    _defaults = {
        'company_id': lambda self, cr, uid, context: self.pool.get('res.company')._company_default_get(cr, uid, 'resource.calendar', context=context)
    }
    
    def get_rest_days(self, cr, uid, t_id, context=None):
        '''If the rest day(s) have been explicitly specified that's what is returned, otherwise
        a guess is returned based on the week days that are not scheduled. If an explicit
        rest day(s) has not been specified an empty list is returned. If it is able to figure
        out the rest days it will return a list of week day integers with Monday being 0.'''
        
        res = []
        tpl =  self.browse(cr, uid, t_id, context=context)
        if tpl.restday_ids:
            res = [rd.sequence for rd in tpl.restday_ids]
        else:
            weekdays = ['0','1','2','3','4','5','6']
            scheddays = []
            scheddays = [wt.dayofweek for wt in tpl.worktime_ids if wt.dayofweek not in scheddays]
            res = [int(d) for d in weekdays if d not in scheddays]
            # If there are no work days return nothing instead of *ALL* the days in the week
            if len(res) == 7:
                res = []
        
        return res
    
    def get_hours_by_weekday(self, cr, uid, tpl_id, day_no, context=None):
        ''' Return the number working hours in the template for day_no.
        For day_no 0 is Monday.'''
        
        delta = timedelta(seconds=0)
        tpl = self.browse(cr, uid, tpl_id, context=context)
        for worktime in tpl.worktime_ids:
            if int(worktime.dayofweek) != day_no:
                continue
            
            fromHour, fromSep, fromMin = worktime.hour_from.partition(':')
            toHour, toSep, toMin = worktime.hour_to.partition(':')
            if len(fromSep) == 0 or len(toSep) == 0:
                raise osv.except_osv('Invalid Data', 'Format of working hours is incorrect')
            
            delta += datetime.strptime(toHour+':'+toMin, '%H:%M') - datetime.strptime(fromHour+':'+fromMin, '%H:%M')
        
        return float(delta.seconds / 60) / 60.0

class hr_schedule_working_times(osv.osv):
    
    _name = "hr.schedule.template.worktime"
    _description = "Work Detail"

    _columns = {
        'name' : fields.char("Name", size=64, required=True),
        'dayofweek': fields.selection(DAYOFWEEK_SELECTION, 'Day of Week', required=True, select=True),
        'sequence': fields.integer('Sequence', required=True),
        'hour_from' : fields.char('Work From', size=5, required=True, select=True),
        'hour_to' : fields.char("Work To", size=5, required=True),
        'template_id' : fields.many2one('hr.schedule.template', 'Schedule Template', required=True),
    }

    _order = 'dayofweek, sequence'
    
    _sql_constraints = [
        ('unique_template_day_from', 'UNIQUE(template_id, dayofweek, hour_from)', 'Duplicate Records!'),
        ('unique_template_day_to', 'UNIQUE(template_id, dayofweek, hour_to)', 'Duplicate Records!'),
    ]

    _defaults = {
        'dayofweek' : '0'
    }

class schedule_ot(osv.Model):
    
    _name = 'hr.schedule.ot'
    _description = 'Schedule OT Wizard'
    
    _inherit = ['ir.needaction_mixin']
    
    _columns = {
        'notes': fields.text('Memo'),
        'employee_id': fields.many2one('hr.employee', 'Employee', required=True, readonly=True,
                                       states={'draft': [('readonly', False)]}),
        'department_id': fields.related('employee_id', 'department_id', relation='hr.department',
                                        type='many2one', store=True, string='Department'),
        'week_start': fields.date('Start of Week', required=True, readonly=True,
                                  states={'draft': [('readonly', False)]}),
        'batch_id': fields.many2one('hr.schedule.ot.batch', 'Batch', readonly=True, ondelete='cascade'),
        'schedule_id': fields.many2one('hr.schedule', 'Schedule', readonly=True),
        'state': fields.selection([
                                   ('draft', 'Draft'),
                                   ('confirm', 'Confirmed'),
                                   ('approve', 'Approved'),
                                   ('decline', 'Declined')
                                  ], 'State', readonly=True),
        'mon': fields.float('Mon.', readonly=True, states={'draft': [('readonly', False)]}),
        'tue': fields.float('Tue.', readonly=True, states={'draft': [('readonly', False)]}),
        'wed': fields.float('Wed.', readonly=True, states={'draft': [('readonly', False)]}),
        'thu': fields.float('Thu.', readonly=True, states={'draft': [('readonly', False)]}),
        'fri': fields.float('Fri.', readonly=True, states={'draft': [('readonly', False)]}),
        'sat': fields.float('Sat.', readonly=True, states={'draft': [('readonly', False)]}),
        'sun': fields.float('Sun.', readonly=True, states={'draft': [('readonly', False)]}),
    }
    
    def _get_employee(self, cr, uid, context=None):
        
        if context == None:
            context = {}
        employee_id = context.get('active_id', False)
        
        return employee_id
    
    _defaults = {
        'state': 'draft',
        'employee_id': _get_employee,
        'mon': 0,
        'tue': 0,
        'wed': 0,
        'thu': 0,
        'fri': 0,
        'sat': 0,
        'sun': 0,
    }
    
    _rec_name = 'week_start'
    _order = 'week_start desc'
    
    def _employee_ot_week_check(self, cr, uid, ids, context=None):
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        data = self.read(cr, uid, ids[0], ['week_start', 'employee_id'], context=context)
        conflict_ids = self.search(cr, uid, [('id', '!=', ids[0]),
                                             ('employee_id', '=', data['employee_id'][0]),
                                             ('week_start', '=', data['week_start'])],
                                   context=context)
        if len(conflict_ids) == 0:
            return True
        
        return False
    
    _constraints = [(_employee_ot_week_check, "Employee already has an OT record for this week.", ['week_start', 'name'])]
    
    def _needaction_domain_get(self, cr, uid, context=None):
        
        users_obj = self.pool.get('res.users')
        domain = []
        
        if users_obj.has_group(cr, uid, 'hr_schedule.group_ot_approve'):
            domain = [('state', 'in', ['confirm'])]
            return domain
        
        if users_obj.has_group(cr, uid, 'hr_schedule.group_ot_schedule') or users_obj.has_group(cr, uid, 'hr_schedule.group_ot_clerk'):
            domain = [('state', 'in', ['draft'])]
            return domain
        
        return False
    
    def onchange_weekstart(self, cr, uid, ids, newdate, context=None):
        
        res = {'value': {'week_start': newdate}}
        if newdate:
            d = datetime.strptime(newdate, OE_DFORMAT)
            if d.weekday() != 0:
                res['value']['week_start'] = False
        return res
    
    def onchange_ot(self, cr, uid, ids, ee_id, week_start, dayofweek, context=None):
        
        res = {}
        if not ee_id or not week_start:
            return res
        
        dayname = False
        if dayofweek == 0:
            dayname = 'mon'
        elif dayofweek == 1:
            dayname = 'tue'
        elif dayofweek == 2:
            dayname = 'wed'
        elif dayofweek == 3:
            dayname = 'thu'
        elif dayofweek == 4:
            dayname = 'fri'
        elif dayofweek == 5:
            dayname = 'sat'
        elif dayofweek == 6:
            dayname = 'sun'
        else:
            return res
        
        dt = datetime.strptime(week_start, OE_DFORMAT) + timedelta(days= +dayofweek)
        rest_days = self.pool.get('hr.schedule').get_rest_days(cr, uid, ee_id, dt, context=context)
        sched_hours = self.pool.get('hr.schedule.detail').scheduled_hours_on_day(cr, uid, ee_id,
                                                                                 None, dt.date(),
                                                                                 context=context)
        if dayofweek in rest_days or sched_hours < 0.01:
            ee = self.pool.get('hr.employee').browse(cr, uid, ee_id, context=context)
            worked_hours = self.pool.get('hr.attendance').total_hours_on_day(cr, uid, ee.contract_id,
                                                                             dt.date(),
                                                                             punches_list=None,
                                                                             context=None)
            if worked_hours < 0.01:
                res.update({'value': {dayname: 0}})
        return res
    
    def action_schedule_ot(self, cr, uid, ids, context=None):
        
        sched_obj = self.pool.get('hr.schedule')
        sched_detail_obj = self.pool.get('hr.schedule.detail')

        if isinstance(ids, (int, long)):
            ids = [ids]
        
        # Modify schedules accordingly
        #
        for sched_ot in self.browse(cr, uid, ids, context=context):
            
            # Find right schedule
            if sched_ot.schedule_id:
                sched_ids = [sched_ot.schedule_id.id]
            else:
                sched_ids = sched_obj.search(cr, uid, ['&', ('date_start', '<=', sched_ot.week_start),
                                                            ('date_end', '>', sched_ot.week_start),
                                                       ('employee_id', '=', sched_ot.employee_id.id)],
                                             context=context)
            if len(sched_ids) == 0:
                raise osv.except_osv(_('Error!'),
                                     _('Employee %s does not have a schedule for the week of %s.')
                                       %(sched_ot.employee_id.name, sched_ot.week_start))
            
            # Get the correct amount of minutes for each day of week and modify the last
            # sign-out time for that day.
            #
            dWeekStart = datetime.strptime(sched_ot.week_start, OE_DFORMAT).date()
            for i in range(0, 7):
                
                hours = 0
                minutes = 0
                dToday = dWeekStart + timedelta(days= +i)
                if i == 0 and sched_ot.mon < 0.01:
                    continue
                elif i == 0:
                    hours = int(math.floor(sched_ot.mon))
                    minutes = float(int(round((sched_ot.mon % 1) * 100))) / 100.0
                    minutes = int(round(minutes * 60.0)) + (hours * 60)
                elif i == 1 and sched_ot.tue < 0.01:
                    continue
                elif i == 1:
                    hours = int(math.floor(sched_ot.tue))
                    minutes = float(int(round((sched_ot.tue % 1) * 100))) / 100.0
                    minutes = int(round(minutes * 60.0)) + (hours * 60)
                elif i == 2 and sched_ot.wed < 0.01:
                    continue
                elif i == 2:
                    hours = int(math.floor(sched_ot.wed))
                    minutes = float(int(round((sched_ot.wed % 1) * 100))) / 100.0
                    minutes = int(round(minutes * 60.0)) + (hours * 60)
                elif i == 3 and sched_ot.thu < 0.01:
                    continue
                elif i == 3:
                    hours = int(math.floor(sched_ot.thu))
                    minutes = float(int(round((sched_ot.thu % 1) * 100))) / 100.0
                    minutes = int(round(minutes * 60.0)) + (hours * 60)
                elif i == 4 and sched_ot.fri < 0.01:
                    continue
                elif i == 4:
                    hours = int(math.floor(sched_ot.fri))
                    minutes = float(int(round((sched_ot.fri % 1) * 100))) / 100.0
                    minutes = int(round(minutes * 60.0)) + (hours * 60)
                elif i == 5 and sched_ot.sat < 0.01:
                    continue
                elif i == 5:
                    hours = int(math.floor(sched_ot.sat))
                    minutes = float(int(round((sched_ot.sat % 1) * 100))) / 100.0
                    minutes = int(round(minutes * 60.0)) + (hours * 60)
                elif i == 6 and sched_ot.sun < 0.01:
                    continue
                elif i == 6:
                    hours = int(math.floor(sched_ot.sun))
                    minutes = float(int(round((sched_ot.sun % 1) * 100))) / 100.0
                    minutes = int(round(minutes * 60.0)) + (hours * 60)
                
                detail_ids = sched_detail_obj.search(cr, uid, [('schedule_id', '=', sched_ids[0]),
                                                               ('dayofweek', '=', str(i)),
                                                               ('day', '=', dToday.strftime(OE_DFORMAT))],
                                                     order='name', context=context)
                if len(detail_ids) == 0:
                    _num, day_name = DAYOFWEEK_SELECTION[i]
                    raise osv.except_osv(_('Error!'),
                                         _('Employee %s does not have a schedule detail for %s.')
                                           %(sched_ot.employee_id.name, day_name))
                
                detail_id = detail_ids[-1]
                data = sched_detail_obj.read(cr, uid, detail_id, ['date_end', 'action'],
                                             context=context)

                # Modify scheduled end time and link OT authorization to schedule
                #
                dtEnd = datetime.strptime(data['date_end'], OE_DTFORMAT)
                dtEnd += timedelta(minutes= +minutes)
                sched_detail_obj.write(cr, uid, detail_id, {'date_end': dtEnd.strftime(OE_DTFORMAT)},
                                       context=context)
                self.write(cr, uid, sched_ot.id, {'schedule_id': sched_ids[0]}, context=context)
        
        return
    
    def do_signal_confirm(self, cr, uid, ids, context=None):
        
        self.write(cr, uid, ids, {'state': 'confirm'}, context=context)
    
    def do_signal_approve(self, cr, uid, ids, context=None):
        
        self.action_schedule_ot(cr, uid, ids, context=context)
        self.write(cr, uid, ids, {'state': 'approve'}, context=context)
    
    def create(self, cr, uid, vals, context=None):
        
        if vals.get('week_start', False) and vals.get('employee_id', False):
            # Find right schedule
            sched_ids = self.pool.get('hr.schedule').search(cr, uid,
                                                            ['&', ('date_start', '<=', vals['week_start']),
                                                                  ('date_end', '>', vals['week_start']),
                                                             ('employee_id', '=', vals['employee_id'])],
                                                            context=context)
            if len(sched_ids) == 0:
                data = self.pool.get('hr.employee').read(cr, uid, vals['employee_id'], ['name'],
                                                         context=context)
                raise osv.except_osv(_('Error!'),
                                     _('Employee %s does not have a schedule for the week of %s.')
                                       %(data['name'], vals['week_start']))
            
            if len(sched_ids) > 0:
                vals.update({'schedule_id': sched_ids[0]})
        
        return super(schedule_ot, self).create(cr, uid, vals, context=context)
    
    def write(self, cr, uid, ids, vals, context=None):
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        for sched_ot in self.browse(cr, uid, ids, context=context):
            if sched_ot.state in ['approve']:
                raise osv.except_osv(_('The record cannot be modified!'), _('You may not modify an OT Schedule that is in a %s state.\nEmployee: %s') %(sched_ot.state, sched_ot.employee_id.name))
        
        return super(schedule_ot, self).write(cr, uid, ids, vals, context=context)
    
    def unlink(self, cr, uid, ids, context=None):
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        for sched_ot in self.browse(cr, uid, ids, context=context):
            if sched_ot.state in ['confirm', 'approve']:
                raise osv.except_osv(_('The record cannot be deleted!'), _('You may not delete an OT Schedule that is in a %s state.\nEmployee: %s') %(sched_ot.state, sched_ot.employee_id.name))
        
        return super(schedule_ot, self).unlink(cr, uid, ids, context=context)

class batch_schedule_ot(osv.Model):
    
    _name = 'hr.schedule.ot.batch'
    
    _inherit = ['ir.needaction_mixin']
    
    _columns = {
        'name': fields.char('Name', size=64, required=True, readonly=True,
                            states={'draft': [('readonly', False)]}),
        'week_start': fields.date('Start of Week', required=True, readonly=True,
                                  states={'draft': [('readonly', False)]}),
        'schedule_ot_ids': fields.one2many('hr.schedule.ot', 'batch_id', 'OT Schedules',
                                         readonly=True,
                                         states={'draft': [('readonly', False)]}),
        'state': fields.selection([
                                   ('draft', 'Draft'),
                                   ('confirm', 'Confirmed'),
                                   ('approve', 'Approved'),
                                   ('decline', 'Declined')
                                  ], 'State', readonly=True),
    }

    _defaults = {
        'state': 'draft',
    }
    
    def _needaction_domain_get(self, cr, uid, context=None):
        
        users_obj = self.pool.get('res.users')
        domain = []
        
        if users_obj.has_group(cr, uid, 'hr_schedule.group_ot_approve'):
            domain = [('state', 'in', ['confirm'])]
            return domain
        
        if users_obj.has_group(cr, uid, 'hr_schedule.group_ot_schedule') or users_obj.has_group(cr, uid, 'hr_schedule.group_ot_clerk'):
            domain = [('state', 'in', ['draft'])]
            return domain
        
        return False
    
    def onchange_weekstart(self, cr, uid, ids, newdate, context=None):
        
        res = {'value': {'week_start': newdate}}
        if newdate:
            d = datetime.strptime(newdate, OE_DFORMAT)
            if d.weekday() != 0:
                res['value']['week_start'] = False
        return res
    
    def write(self, cr, uid, ids, vals, context=None):
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        for batch in self.browse(cr, uid, ids, context=context):
            if batch.state in ['approve']:
                raise osv.except_osv(_('The record cannot be modified!'), _('You may not modify a Batch Scheduled OT that is in the %s state.') %(batch.state))
        
        res = super(batch_schedule_ot, self).write(cr, uid, ids, vals, context=context)
        
        if vals.get('week_start', False):
            schedot_obj = self.pool.get('hr.schedule.ot')
            for batch in self.browse(cr, uid, ids, context=context):
                sched_ot_ids = [sched_ot.id for sched_ot in batch.schedule_ot_ids]
                if len(sched_ot_ids) > 0:
                    schedot_obj.write(cr, uid, sched_ot_ids, {'week_start': vals['week_start']},
                                      context=context)
        
        return res
    
    def unlink(self, cr, uid, ids, context=None):
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        for batch in self.browse(cr, uid, ids, context=context):
            if batch.state in ['confirm', 'approve']:
                raise osv.except_osv(_('The record cannot be deleted!'), _('You may not delete a Batch Scheduled OT that is in the %s state.') %(batch.state))
        
        return super(batch_schedule_ot, self).unlink(cr, uid, ids, context=context)
    
    def _state(self, cr, uid, ids, signal, state, context=None):
        
        wkf = netsvc.LocalService('workflow')
        for batch in self.browse(cr, uid, ids, context=context):
            [wkf.trg_validate(uid, 'hr.schedule.ot', sched_ot.id, signal, cr) for sched_ot in batch.schedule_ot_ids]
            self.write(cr, uid, batch.id, {'state': state}, context=context)
        
        return True
    
    def state_confirm(self, cr, uid, ids, context=None):
        
        return self._state(cr, uid, ids, 'signal_confirm', 'confirm', context)
    
    def state_approve(self, cr, uid, ids, context=None):
        
        return self._state(cr, uid, ids, 'signal_approve', 'approve', context)
    
    def state_decline(self, cr, uid, ids, context=None):
        
        return self._state(cr, uid, ids, 'signal_decline', 'decline', context)

class contract_init(osv.Model):
    
    _inherit = 'hr.contract.init'
    
    _columns = {
        'sched_template_id': fields.many2one('hr.schedule.template', 'Schedule Template',
                                             readonly=True, states={'draft': [('readonly', False)]}),
    }

class hr_contract(osv.osv):
    
    _name = 'hr.contract'
    _inherit = 'hr.contract'
    
    _columns = {
        'schedule_template_id': fields.many2one('hr.schedule.template','Working Schedule Template', required=True),
    }
    
    def _get_sched_template(self, cr, uid, context=None):
        
        res = False
        init = self.get_latest_initial_values(cr, uid, context=context)
        if init != None and init.sched_template_id:
            res = init.sched_template_id.id
        return res
    
    _defaults = {
        'schedule_template_id': _get_sched_template,
    }
    
    def create(self, cr, uid, vals, context=None):
        
        res = super(hr_contract, self).create(cr, uid, vals, context=context)
        
        ee = self.pool.get('hr.employee').browse(cr, uid, vals['employee_id'], context=context)
        
        # Only create schedule when the employee is first hired
        if len(ee.contract_ids) != 1:
            return res
        
        dToday = datetime.now().date()
        dStart = datetime.strptime(ee.contract_id.date_start, OE_DFORMAT).date()
        # The contract start date may be way back in the past, so use today's date
        # as the start date if the contract started before today.
        if dStart < dToday:
            dStart = dToday
        while dStart.weekday() != 0:
            dStart += timedelta(days= -1)
        
        # Get End date by trying to figure out when the next mass schedule will be created
        #
        res_model, res_id = self.pool.get('ir.model.data').get_object_reference(cr, uid,
                                                                                'hr_schedule',
                                                                                'mass_schedule_cron')
        data = self.pool.get('ir.cron').read(cr, uid, res_id, ['nextcall'], context=context)
        dEnd = datetime.strptime(data['nextcall'], OE_DTFORMAT).date()
        if dEnd < dStart:
            dEnd = dStart
        while dEnd.weekday() != 6:
            dEnd += timedelta(days= +1)
        
        sched = {
            'name': ee.name +': '+ dStart.strftime('%Y-%m-%d') +' Wk '+ str(dStart.isocalendar()[1]),
            'employee_id': ee.id,
            'template_id': ee.contract_id.schedule_template_id.id,
            'date_start': dStart.strftime('%Y-%m-%d'),
            'date_end': dEnd.strftime('%Y-%m-%d'),
        }
        self.pool.get('hr.schedule').create(cr, uid, sched, context=context)
    
        return res

class hr_attendance(osv.osv):
    
    _name = 'hr.attendance'
    _inherit = 'hr.attendance'
    
    _columns = {
        'alert_ids': fields.one2many('hr.schedule.alert', 'punch_id', 'Exceptions', readonly=True),
    }
    
    def _remove_direct_alerts(self, cr, uid, ids, context=None):
        '''Remove alerts directly attached to the attendance and return a unique
        list of tuples of employee ids and attendance dates.'''
        
        alert_obj = self.pool.get('hr.schedule.alert')
        
        # Remove alerts directly attached to the attendances
        #
        alert_ids = []
        attendances = []
        attendance_keys = []
        for attendance in self.browse(cr, uid, ids, context=context):
            [alert_ids.append(alert.id) for alert in attendance.alert_ids]
            key = str(attendance.employee_id.id) + attendance.day
            if key not in attendance_keys:
                attendances.append((attendance.employee_id.id, attendance.day))
                attendance_keys.append(key)
        
        if len(alert_ids) > 0: alert_obj.unlink(cr, uid, alert_ids, context=context)
        
        return attendances
    
    def _recompute_alerts(self, cr, uid, attendances, context=None):
        '''Recompute alerts for each record in attendances.'''
        
        alert_obj = self.pool.get('hr.schedule.alert')
        
        # Remove all alerts for the employee(s) for the day and recompute.
        #
        for ee_id, strDay in attendances:
            
            # Today's records will be checked tomorrow. Future records can't generate alerts.
            if strDay >= fields.date.context_today(self, cr, uid, context=context):
                continue
            
            # XXX - Someone who cares about DST should fix this
            #
            data = self.pool.get('res.users').read(cr, uid, uid, ['tz'], context=context)
            dt = datetime.strptime(strDay + ' 00:00:00', '%Y-%m-%d %H:%M:%S')
            lcldt = timezone(data['tz']).localize(dt, is_dst=False)
            utcdt = lcldt.astimezone(utc)
            utcdtNextDay = utcdt + relativedelta(days= +1)
            strDayStart = utcdt.strftime('%Y-%m-%d %H:%M:%S')
            strNextDay = utcdtNextDay.strftime('%Y-%m-%d %H:%M:%S')
            
            alert_ids = alert_obj.search(cr, uid, [('employee_id', '=', ee_id),
                                                    '&', ('name', '>=', strDayStart),
                                                         ('name', '<', strNextDay)],
                                         context=context)
            alert_obj.unlink(cr, uid, alert_ids, context=context)
            alert_obj.compute_alerts_by_employee(cr, uid, ee_id, strDay, context=context)
    
    def create(self, cr, uid, vals, context=None):
        
        res = super(hr_attendance, self).create(cr, uid, vals, context=context)
        
        obj = self.browse(cr, uid, res, context=context)
        attendances = [(obj.employee_id.id, fields.date.context_today(self, cr, uid, context=context))]
        self._recompute_alerts(cr, uid, attendances, context=context)
        
        return res
    
    def unlink(self, cr, uid, ids, context=None):
        
        # Remove alerts directly attached to the attendances
        #
        attendances = self._remove_direct_alerts(cr, uid, ids, context=context)
        
        res = super(hr_attendance, self).unlink(cr, uid, ids, context=context)
        
        # Remove all alerts for the employee(s) for the day and recompute.
        #
        self._recompute_alerts(cr, uid, attendances, context=context)
        
        return res
    
    def write(self, cr, uid, ids, vals, context=None):
        
        # Flag for checking wether we have to recompute alerts
        trigger_alert = False
        for k, v in vals.iteritems():
            if k in ['name', 'action']:
                trigger_alert = True
        
        if trigger_alert:
            # Remove alerts directly attached to the attendances
            #
            attendances = self._remove_direct_alerts(cr, uid, ids, context=context)
        
        res = super(hr_attendance, self).write(cr, uid, ids, vals, context=context)
        
        if trigger_alert:
            # Remove all alerts for the employee(s) for the day and recompute.
            #
            self._recompute_alerts(cr, uid, attendances, context=context)
        
        return res

class hr_holidays(osv.Model):
    
    _inherit = 'hr.holidays'
    
    def holidays_validate(self, cr, uid, ids, context=None):
        
        res = super(hr_holidays, self).holidays_validate(cr, uid, ids, context=context)
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        unlink_ids = []
        det_obj = self.pool.get('hr.schedule.detail')
        for leave in self.browse(cr, uid, ids, context=context):
            if leave.type != 'remove':
                continue

            det_ids = det_obj.search(cr, uid, [('schedule_id.employee_id', '=', leave.employee_id.id),
                                               ('date_start', '<=', leave.date_to),
                                               ('date_end', '>=', leave.date_from)],
                                     order='date_start', context=context)
            for detail in det_obj.browse(cr, uid, det_ids, context=context):
                
                # Remove schedule details completely covered by leave
                if  leave.date_from <= detail.date_start and leave.date_to >= detail.date_end:
                    if detail.id not in unlink_ids:
                        unlink_ids.append(detail.id)
                
                # Partial day on first day of leave
                elif leave.date_from > detail.date_start and leave.date_from <= detail.date_end:
                    dtLv = datetime.strptime(leave.date_from, OE_DTFORMAT)
                    if leave.date_from == detail.date_end:
                        if detail.id not in unlink_ids:
                            unlink_ids.append(detail.id)
                        else:
                            dtSchedEnd = dtLv + timedelta(seconds= -1)
                            det_obj.write(cr, uid, detail.id, {'date_end': dtSchedEnd.strftime(OE_DTFORMAT)},
                                          context=context)
                
                # Partial day on last day of leave
                elif leave.date_to < detail.date_end and leave.date_to >= detail.date_start:
                    dtLv = datetime.strptime(leave.date_to, OE_DTFORMAT)
                    if leave.date_to != detail.date_start:
                        dtStart = dtLv + timedelta(seconds= +1)
                        det_obj.write(cr, uid, detail.id, {'date_start': dtStart.strftime(OE_DTFORMAT)},
                                      context=context)
        
        det_obj.unlink(cr, uid, unlink_ids, context=context)
        
        return res
    
    def holidays_refuse(self, cr, uid, ids, context=None):
        
        res = super(hr_holidays, self).holidays_refuse(cr, uid, ids, context=context)
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        sched_obj = self.pool.get('hr.schedule')
        for leave in self.browse(cr, uid, ids, context=context):
            if leave.type != 'remove':
                continue
            
            dLvFrom = datetime.strptime(leave.date_from, OE_DTFORMAT).date()
            dLvTo = datetime.strptime(leave.date_to, OE_DTFORMAT).date()
            sched_ids = sched_obj.search(cr, uid, [('employee_id', '=', leave.employee_id.id),
                                                   ('date_start', '<=', dLvTo.strftime(OE_DFORMAT)),
                                                   ('date_end', '>=', dLvFrom.strftime(OE_DFORMAT))])

            # Re-create affected schedules from scratch
            for sched_id in sched_ids:
                sched_obj.delete_details(cr, uid, sched_id, context=context)
                sched_obj.create_details(cr, uid, sched_id, context=context)
        
        return res

class hr_term(osv.Model):
    
    _inherit = 'hr.employee.termination'
    
    def create(self, cr, uid, vals, context=None):
        
        res = super(hr_term, self).create(cr, uid, vals, context=context)
        
        det_obj = self.pool.get('hr.schedule.detail')
        term = self.browse(cr, uid, res, context=context)
        user = self.pool.get('res.users').browse(cr, uid, uid)
        if user and user.tz:
            local_tz = timezone(user.tz)
        else:
            local_tz = timezone('Africa/Addis_Ababa')
        dt = datetime.strptime(term.name + ' 00:00:00', OE_DTFORMAT)
        utcdt = (local_tz.localize(dt, is_dst=False)).astimezone(utc)
        det_ids = det_obj.search(cr, uid, [('schedule_id.employee_id', '=', term.employee_id.id),
                                           ('date_start', '>=', utcdt.strftime(OE_DTFORMAT))],
                                 order='date_start', context=context)
        det_obj.unlink(cr, uid, det_ids, context=context)
        
        return res
    
    def _restore_schedule(self, cr, uid, ids, context=None):
        
        if isinstance(ids, (int, long)):
            ids = [ids]
        
        sched_obj = self.pool.get('hr.schedule')
        for term in self.browse(cr, uid, ids, context=context):
            d = datetime.strptime(term.name, OE_DFORMAT).date()
            sched_ids = sched_obj.search(cr, uid, [('employee_id', '=', term.employee_id.id),
                                                   ('date_end', '>=', d.strftime(OE_DFORMAT))])

            # Re-create affected schedules from scratch
            for sched_id in sched_ids:
                sched_obj.delete_details(cr, uid, sched_id, context=context)
                sched_obj.create_details(cr, uid, sched_id, context=context)
        
        return
    
    def state_cancel(self, cr, uid, ids, context=None):
        
        self._restore_schedule(cr, uid, ids, context=context)
        res = super(hr_term, self).state_cancel(cr, uid, ids, context=context)
        return res

    def unlink(self, cr, uid, ids, context=None):
        
        self._restore_schedule(cr, uid, ids, context=context)
        res = super(hr_term, self).unlink(cr, uid, ids, context=context)
        return res
