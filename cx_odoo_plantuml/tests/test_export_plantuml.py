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

from odoo.exceptions import UserError
from odoo.tests import Form
from odoo.tests.common import TransactionCase


class TestExportPlantuml(TransactionCase):
    """export_plantuml test class"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.export_wiz_model = cls.env["cx.plantuml.export.wiz"]
        cls.module_model = cls.env["ir.module.module"]
        cls.installed_module = cls.env["ir.module.module"].search(
            [("state", "=", "installed")]
        )[1]
        cls.show_installed_module = cls.env["cx.plantuml.export.wiz"].create(
            {"module_id": cls.installed_module.id}
        )
        cls.uninstalled_module = cls.env["ir.module.module"].search(
            [("state", "=", "uninstalled")]
        )[1]
        cls.show_uninstalled_module = cls.env["cx.plantuml.export.wiz"].create(
            {"module_id": cls.uninstalled_module.id}
        )

    def test_install_module_wizard_form(self):
        """Testing installed field from wizard form"""
        with Form(self.show_installed_module) as wizard_form:
            self.assertEqual(wizard_form.installed, True)
            self.assertEqual(wizard_form.show_fields, False)
            self.assertEqual(wizard_form.show_inherited, False)

        with Form(self.show_uninstalled_module) as wizard_form:
            self.assertEqual(wizard_form.installed, False)
            self.assertEqual(wizard_form.show_fields, False)
            self.assertEqual(wizard_form.show_inherited, False)

    def test_onchange_not_installed(self):
        """Testing _compute_installed function"""
        export_module = self.show_uninstalled_module
        export_module._compute_installed()
        self.assertFalse(export_module.installed)
        export_module = self.show_uninstalled_module
        self.uninstalled_module["state"] = "installed"
        export_module._compute_installed()
        self.assertTrue(export_module.installed)

    def test_onchange_show_fields(self):
        """Testing show_pro_warning function"""
        export_wiz = self.show_installed_module
        export_wiz.show_fields = True
        with self.assertRaises(UserError):
            export_wiz.show_pro_warning()

    def test_download_uml_installed(self):
        """Testing download_uml function"""
        export_module = self.show_installed_module
        result = export_module.download_uml()
        download = self.env["cx.plantuml.export.wiz.download"].browse(result["res_id"])
        self.assertIsNotNone(download)
        self.assertEqual(
            result["name"],
            (export_module.module_id.shortdesc + " module PlantUML files"),
        )
        self.assertEqual(result["type"], "ir.actions.act_window")
        self.assertEqual(result["res_model"], "cx.plantuml.export.wiz.download")
        self.assertEqual(result["target"], "new")
        self.assertEqual(
            result["view_id"],
            self.env.ref("cx_odoo_plantuml.cetmix_uml_export_download_form").id,
        )
        self.assertEqual(result["view_mode"], "form")
