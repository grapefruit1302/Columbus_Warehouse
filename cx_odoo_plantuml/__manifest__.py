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

{
    "name": "Odoo UML PlantUML Export",
    "version": "18.0.1.0.0",
    "summary": "Export Odoo to UML PlantUML Module Diagram Structure",
    "author": "Cetmix, Ivan Sokolov",
    "maintainer": "Cetmix",
    "license": "LGPL-3",
    "category": "Extra Tools",
    "website": "https://cetmix.com",
    "live_test_url": "https://cetmix.com",
    "images": ["static/description/banner.png"],
    "depends": ["base_setup"],
    "data": [
        "data/default_config_parameters.xml",
        "security/ir.model.access.csv",
        "views/ir_module.xml",
        "views/res_config_settings_view.xml",
        "wizard/export_plantuml_wizard_view.xml",
        "wizard/export_plantuml_download_wizard_view.xml",
    ],
    "installable": True,
    "application": True,
}
