###################################################################################
#
#    Copyright (C) 2020 Cetmix OÜ
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU LESSER GENERAL PUBLIC LICENSE as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###################################################################################

from odoo import fields, models


###################
# Config Settings #
###################
class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    cetmix_plantuml_server_url = fields.Char(
        string="Server URL",
        config_parameter="cx_odoo_plantuml.cetmix_plantuml_server_url",
    )
    cx_max_selection = fields.Integer(
        string="Max Selection Options",
        help="If the number of options for Selection field exceeds this amount"
        " it will be shortened to 'x options'",
        config_parameter="cx_odoo_plantuml.max_selection",
    )
