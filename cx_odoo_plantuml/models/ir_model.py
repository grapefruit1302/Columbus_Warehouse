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

from odoo import models


#########
# Model #
#########
class Model(models.Model):
    _inherit = "ir.model"

    # -- Get name and inherit
    def is_inherited(self, module_list):
        """
        Check if module is declared earlier in the module list.
        :param  module_list: list of model names (e.g. ['base', 'sale_management'...])
        :return: dict of {model: Inherited}
         (e.g. {'res.partner': True, 'my.model': False, ...}
        """
        res = {}
        for rec in self:
            inherited = False
            model_modules = rec.get_modules()
            if model_modules:
                for module in module_list:
                    if module in model_modules:
                        inherited = True
                        break
            res.update({rec.model: inherited})
        return res

    # -- Return a set of modules model id present in
    def get_modules(self):
        xml_ids = models.Model._get_external_ids(self)
        module_names = {xml_id.split(".")[0] for xml_id in xml_ids[self.id]}
        return module_names
