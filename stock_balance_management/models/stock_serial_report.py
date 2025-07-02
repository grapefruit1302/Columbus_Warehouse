from odoo import models, fields, tools

class StockSerialReport(models.Model):
    _name = 'stock.serial.report'
    _description = 'Звіт по серійних номерах'
    _auto = False

    nomenclature_id = fields.Many2one('product.nomenclature', 'Номенклатура')
    nomenclature_name = fields.Char('Назва товару')
    serial_number = fields.Char('Серійний номер')
    location_type = fields.Selection([
        ('warehouse', 'Склад'),
        ('employee', 'Працівник'),
    ], 'Тип локації')
    warehouse_name = fields.Char('Склад')
    employee_name = fields.Char('Працівник')
    company_id = fields.Many2one('res.company', 'Компанія')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT 
                    row_number() OVER () AS id,
                    sb.nomenclature_id,
                    pn.name AS nomenclature_name,
                    regexp_split_to_table(sb.serial_numbers, E'[,\\n]') AS serial_number,
                    sb.location_type,
                    sw.name AS warehouse_name,
                    he.name AS employee_name,
                    sb.company_id
                FROM stock_balance sb
                LEFT JOIN product_nomenclature pn ON pn.id = sb.nomenclature_id
                LEFT JOIN stock_warehouse sw ON sw.id = sb.warehouse_id
                LEFT JOIN hr_employee he ON he.id = sb.employee_id
                WHERE sb.serial_numbers IS NOT NULL
                AND sb.serial_numbers != ''
                AND sb.qty_available > 0
            )
        """ % self._table)