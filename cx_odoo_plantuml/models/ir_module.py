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

from odoo import api, models

from . import templates
from .templates import MAX_NAME_LEN, MAX_NAME_WORDS

INSTALLED = ["installed", "to upgrade"]
PAID = ["OPL-1", "Other proprietary"]  # Paid licences
EE = ["OEEL-1"]  # Odoo Enterprise licences
CHARS_REMOVE = ["(", ")", "{", "}", "!", ""]


# -- Sanitize text val
def sanitize_val(val):
    """
    Remove all unwanted characters from string
    """
    for symbol in CHARS_REMOVE:
        val = val.replace(symbol, "")
    return val


##########
# Module #
##########
class Module(models.Model):
    _inherit = "ir.module.module"

    # -- Model name to class name
    @api.model
    def model_name_2_class_name(self, model_name):
        """
        Convert model.name to ClassName
        model name Char: res.partner
        returns class_name Char: ResPartner
        """
        mod_name = []
        for part in model_name.split("."):
            mod_name.append(part.capitalize())
        return "".join(mod_name)

    @api.model
    # -- Compose module class
    def parse_module_class(self, module, class_type="Module"):
        """
        class_type 'Root', 'App' or 'Module'
        Parses a class and returns formatted UML
        """
        # Set module licence value
        module_license = module.get("license", "Undefined")
        if module_license in EE:
            license_label = "ee(Enterprise)"
        elif module_license in PAID:
            license_label = f"paid({module_license})"
        else:
            license_label = f"free({module_license})"

        # Compose installation status
        state = module["state"]
        if state in INSTALLED:
            stale_label = f"installed({state})"
        else:
            stale_label = f"not_installed({state})"
        if module["auto"]:  # Auto-install?
            stale_label = ", ".join((stale_label, "<i>auto</i>"))

        name = module["name"]

        # Shorten long module names
        if len(name) > MAX_NAME_LEN:
            name_list = name.split(" ")
            name = " ".join(name_list[:MAX_NAME_WORDS])

        body = templates.MODULE_TEMPLATE.format(
            class_type,
            module["tech_name"],
            name,
            module["tech_name"],
            stale_label,
            module["version"],
            license_label,
            module["author"],
        )
        return body

    # -- Compose relations
    @api.model
    def parse_rel(self, rel):
        """
        Parses relation and returns formatted UML
        """
        body = templates.RELATION_TEMPLATE.format(rel[0], rel[1])
        return body

    # -- Compose dependencies UML from vals
    @api.model
    def compose_uml_modules(self, root, modules, deps):
        """
        Compose module dependencies UML

        root Dict root node
        modules: array of Dict of modules
        deps: array of tuples (child, parent)
        """
        prefix = "\n".join(
            (" ".join(("@startuml", root["name"])), templates.MODULE_PREFIX)
        )
        entries = [self.parse_module_class(root, "Root")]

        # Add modules
        for module in modules:
            module_type = "App" if module["app"] else "Module"
            entries.append(self.parse_module_class(module, module_type))

        # Add relations
        for rel in deps:
            entries.append(self.parse_rel(rel))

        uml = "\n".join((prefix, "\n".join(entries), "@enduml"))
        return uml

    # -- Collect Module dependencies data
    def module_collect_deps(self):
        """
        Compose module dependencies dicts
        Returns root dict: Current Module, modules dict:
        Modules depends on, deps array of tuples: Dependencies
        """

        # Parse module
        def parse_module(module):
            vals = {
                "name": sanitize_val(module.shortdesc),
                "tech_name": sanitize_val(module.name),
                "author": sanitize_val(module.author),
                "version": module.installed_version,
                "app": module.application,
                "license": sanitize_val(module.license),
                "state": module.state,
                "auto": module.auto_install,
            }
            return vals

        # Get dependencies
        def get_children(module, parent_name=False):
            for child in module.dependencies_id.mapped("depend_id"):
                child_name = child.name
                if child_name not in modules_found:
                    modules.append(parse_module(child))
                    modules_found.append(child_name)
                    get_children(child, child_name)
                if (parent_name, child_name) not in deps:
                    deps.append((parent_name, child_name))

        modules = []  # Array of dicts of module vals
        deps = []  # Array of dicts of module relations
        modules_found = [self.name]  # Array of modules already found
        get_children(self, self.name)
        root = parse_module(self)
        return root, modules, deps, modules_found

    # -- Parse model vals into PlantUML Class
    @api.model
    def parse_model_class(self, model):
        vals = templates.MODEL_TEMPLATE.format(
            "TransientModel" if model["transient"] else "Model",
            model["class_name"],
            model["description"],
            model["name"],
        )
        return vals

    # -- Compose dependencies UML from vals
    @api.model
    def compose_uml_models(self, model_vals, module_name="Module"):
        """
        Compose module classes UML

        model_vals [Dict]: list of model vals
        """
        prefix = "\n".join(
            (" ".join(("@startuml", module_name)), templates.MODEL_PREFIX)
        )
        models_new = []
        models_inherited = []
        for mod in model_vals:
            inherited = mod["inherited"]
            res = self.parse_model_class(mod)
            if inherited:
                models_inherited.append(res)
            else:
                models_new.append(res)
        models_new_uml = (
            "\n".join(
                (
                    (templates.PACKAGE_NEW % self.env._("New")),
                    "\n".join(models_new),
                    "}\n",
                )
            )
            if models_new
            else ""
        )
        models_inherited_uml = (
            "\n".join(
                (
                    (templates.PACKAGE_INHERITED % self.env._("Inherited")),
                    "\n".join(models_inherited),
                    "}\n",
                )
            )
            if models_new
            else ""
        )

        uml = "\n".join((prefix, models_new_uml, models_inherited_uml, "@enduml"))
        return uml

    # -- Collect Models data
    def module_collect_models(self, modules_found=False):
        module_name = self.name
        model_refs = self.env["ir.model.data"].search(
            [
                ("module", "=", module_name),
                ("model", "=", "ir.model"),
            ]
        )
        model_models = self.env["ir.model"].browse(model_refs.mapped("res_id"))
        model_vals = []
        model_inherited = model_models.is_inherited(
            [mod for mod in modules_found if not mod == module_name]
        )

        # Compose vals array
        for mod in model_models:
            mod_model = mod.model
            vals = {
                "class_name": self.model_name_2_class_name(mod_model),
                "description": mod.name,
                "name": mod_model,
                "inherited": model_inherited[mod_model],
                "transient": mod.transient,
            }
            model_vals.append(vals)

        return model_vals

    # -- Button Get PlantUML Data
    def button_plantuml_export(self):
        self.ensure_one()
        return {
            "name": self.env._("Export PlantUML"),
            "views": [[False, "form"]],
            "res_model": "cx.plantuml.export.wiz",
            "type": "ir.actions.act_window",
            "target": "new",  # current for same view
        }

    # -- Get module dependencies UML
    def get_uml_deps(self):
        """
        Returns formatted UML
        """
        root, parent_structure, parent_deps, modules_found = self.module_collect_deps()
        uml = self.compose_uml_modules(root, parent_structure, parent_deps)
        return uml, modules_found

    # -- Get module models UML
    def get_uml_models(self, modules_found=False, pro=False):
        uml = self.compose_uml_models(
            self.module_collect_models(modules_found), self.name
        )
        return uml
