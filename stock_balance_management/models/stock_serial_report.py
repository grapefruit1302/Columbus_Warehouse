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
    
    # ДОДАЄМО нові поля
    batch_number = fields.Char('Партія')
    document_reference = fields.Char('Документ')
    source_document_type = fields.Char('Тип документу')
    
    company_id = fields.Many2one('res.company', 'Компанія')
    qty_available = fields.Float('Доступна кількість')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT 
                    row_number() OVER () AS id,
                    sb.nomenclature_id,
                    pn.name AS nomenclature_name,
                    serial_data.serial_number,
                    sb.location_type,
                    sw.name AS warehouse_name,
                    he.name AS employee_name,
                    COALESCE(batch.batch_number, '') AS batch_number,
                    COALESCE(batch.source_document_number, '') AS document_reference,
                    CASE 
                        WHEN batch.source_document_type = 'receipt' THEN 'Прихідна накладна'
                        WHEN batch.source_document_type = 'inventory' THEN 'Акт оприходування'
                        WHEN batch.source_document_type = 'return' THEN 'Повернення з сервісу'
                        ELSE COALESCE(batch.source_document_type, '')
                    END AS source_document_type,
                    sb.company_id,
                    sb.qty_available
                FROM stock_balance sb
                LEFT JOIN product_nomenclature pn ON pn.id = sb.nomenclature_id
                LEFT JOIN stock_warehouse sw ON sw.id = sb.warehouse_id
                LEFT JOIN hr_employee he ON he.id = sb.employee_id
                LEFT JOIN stock_batch batch ON batch.id = sb.batch_id
                CROSS JOIN LATERAL (
                    SELECT trim(serial) AS serial_number
                    FROM unnest(string_to_array(replace(sb.serial_numbers, E'\n', ','), ',')) AS serial
                    WHERE trim(serial) != ''
                ) AS serial_data
                WHERE sb.serial_numbers IS NOT NULL
                AND sb.serial_numbers != ''
                AND sb.qty_available > 0
                ORDER BY pn.name, serial_data.serial_number
            )
        """ % self._table)