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


class DownloadUML(models.TransientModel):
    _name = "cx.plantuml.export.wiz.download"
    _description = "PlantUML Export Wizard - Download"

    deps = fields.Binary(string="Dependencies (Download)", attachment=False)
    deps_fname = fields.Char(string="Dependencies Filename")

    models = fields.Binary(string="Module Models (Download)", attachment=False)
    models_fname = fields.Char(string="Module Models Filename")

    installed = fields.Boolean()
