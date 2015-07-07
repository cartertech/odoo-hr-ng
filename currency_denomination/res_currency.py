# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014-2015 Michael Telahun Makonnen <mmakonnen@gmail.com> and
#    One Click Software <http://oneclick.solutions>.
#    All Rights Reserved.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
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

from openerp.addons.decimal_precision import decimal_precision as dp
from openerp.osv import fields, orm

class res_currency_denomination(orm.Model):
    
    _name = 'res.currency.denomination'
    _description = 'Currency Denomination'
    
    _columns = {
        'currency_id': fields.many2one('res.currency', 'Currency', required=True),
        'ratio': fields.float('Ratio', help="Ratio of this denomination to the smallest integral denomination."),
        'value': fields.float('Value', digits_compute=dp.get_precision('Account')),
    }
    
    _rec_name = 'value'

class res_currency(orm.Model):
    
    _inherit = 'res.currency'
    
    _columns = {
        'denomination_ids': fields.one2many('res.currency.denomination', 'currency_id',
                                            'Denominations'),
    }
