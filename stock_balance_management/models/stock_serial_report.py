from odoo import models, fields, tools, api
import logging

_logger = logging.getLogger(__name__)

class StockSerialReport(models.Model):
    _name = 'stock.serial.report'
    _description = 'Звіт по серійних номерах'
    _auto = False
    _rec_name = 'serial_number'

    nomenclature_id = fields.Many2one('product.nomenclature', 'Номенклатура')
    nomenclature_name = fields.Char('Назва товару')
    serial_number = fields.Char('Серійний номер')
    location_type = fields.Selection([
        ('warehouse', 'Склад'),
        ('employee', 'Працівник'),
    ], 'Тип локації')
    warehouse_name = fields.Char('Склад')
    employee_name = fields.Char('Працівник')
    
    # Додаткові поля
    batch_number = fields.Char('Партія')
    document_reference = fields.Char('Документ')
    source_document_type = fields.Char('Тип документу')
    
    company_id = fields.Many2one('res.company', 'Компанія')
    qty_available = fields.Float('Доступна кількість')

    def init(self):
        """Створення SQL view для звіту"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        
        try:
            sql_query = """
                CREATE OR REPLACE VIEW {} AS (
                    SELECT 
                        row_number() OVER (ORDER BY sb.id, serial_line.serial_number) AS id,
                        sb.nomenclature_id,
                        COALESCE(pn.name, 'Unknown Product') AS nomenclature_name,
                        serial_line.serial_number,
                        sb.location_type,
                        COALESCE(sw.name, '') AS warehouse_name,
                        COALESCE(he.name, '') AS employee_name,
                        COALESCE(batch.batch_number, '') AS batch_number,
                        COALESCE(batch.source_document_number, '') AS document_reference,
                        CASE 
                            WHEN batch.source_document_type = 'receipt' THEN 'Receipt'
                            WHEN batch.source_document_type = 'inventory' THEN 'Inventory'
                            WHEN batch.source_document_type = 'return' THEN 'Return'
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
                        SELECT DISTINCT trim(serial_num) AS serial_number
                        FROM unnest(
                            string_to_array(
                                replace(COALESCE(sb.serial_numbers, ''), E'\\n', ','), 
                                ','
                            )
                        ) AS serial_num
                        WHERE trim(serial_num) != '' AND trim(serial_num) IS NOT NULL
                    ) AS serial_line
                    WHERE sb.serial_numbers IS NOT NULL
                    AND sb.serial_numbers != ''
                    AND sb.qty_available > 0
                    ORDER BY pn.name, serial_line.serial_number
                )
            """.format(self._table)
            
            self.env.cr.execute(sql_query)
            _logger.info(f"Successfully created view {self._table}")
            
        except Exception as e:
            _logger.error(f"Помилка створення view stock_serial_report: {e}")
            # Створюємо простішу view як fallback
            try:
                fallback_sql = """
                    CREATE OR REPLACE VIEW {} AS (
                        SELECT 
                            sb.id,
                            sb.nomenclature_id,
                            COALESCE(pn.name, 'Unknown Product') AS nomenclature_name,
                            'Data Unavailable' AS serial_number,
                            sb.location_type,
                            COALESCE(sw.name, '') AS warehouse_name,
                            COALESCE(he.name, '') AS employee_name,
                            '' AS batch_number,
                            '' AS document_reference,
                            '' AS source_document_type,
                            sb.company_id,
                            sb.qty_available
                        FROM stock_balance sb
                        LEFT JOIN product_nomenclature pn ON pn.id = sb.nomenclature_id
                        LEFT JOIN stock_warehouse sw ON sw.id = sb.warehouse_id
                        LEFT JOIN hr_employee he ON he.id = sb.employee_id
                        WHERE sb.serial_numbers IS NOT NULL
                        AND sb.serial_numbers != ''
                        AND sb.qty_available > 0
                        LIMIT 0
                    )
                """.format(self._table)
                
                self.env.cr.execute(fallback_sql)
                _logger.info(f"Created fallback view {self._table}")
            except Exception as fallback_error:
                _logger.error(f"Fallback view creation failed: {fallback_error}")
                final_fallback = """
                    CREATE OR REPLACE VIEW {} AS (
                        SELECT 
                            1 AS id,
                            NULL::integer AS nomenclature_id,
                            'Loading Error' AS nomenclature_name,
                            'Error' AS serial_number,
                            'warehouse' AS location_type,
                            '' AS warehouse_name,
                            '' AS employee_name,
                            '' AS batch_number,
                            '' AS document_reference,
                            '' AS source_document_type,
                            1::integer AS company_id,
                            0::float AS qty_available
                        WHERE FALSE
                    )
                """.format(self._table)
                self.env.cr.execute(final_fallback)

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """Перевизначаємо search_read для перекладу значень та кращої обробки помилок"""
        try:
            result = super().search_read(domain, fields, offset, limit, order)
            
            # Перекладаємо значення source_document_type та nomenclature_name
            for record in result:
                if 'source_document_type' in record:
                    if record['source_document_type'] == 'Receipt':
                        record['source_document_type'] = 'Прихідна накладна'
                    elif record['source_document_type'] == 'Inventory':
                        record['source_document_type'] = 'Акт оприходування'
                    elif record['source_document_type'] == 'Return':
                        record['source_document_type'] = 'Повернення з сервісу'
                
                if 'nomenclature_name' in record and record['nomenclature_name'] == 'Unknown Product':
                    record['nomenclature_name'] = 'Невідомий товар'
            
            return result
        except Exception as e:
            _logger.error(f"Помилка в search_read для stock_serial_report: {e}")
            # Повертаємо порожній результат замість помилки
            return []

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        """Перевизначаємо read_group для групування з перекладами"""
        try:
            result = super().read_group(domain, fields, groupby, offset, limit, orderby, lazy)
            
            # Перекладаємо значення в групуванні
            for group in result:
                if 'source_document_type' in group:
                    if group['source_document_type'] == 'Receipt':
                        group['source_document_type'] = 'Прихідна накладна'
                    elif group['source_document_type'] == 'Inventory':
                        group['source_document_type'] = 'Акт оприходування'  
                    elif group['source_document_type'] == 'Return':
                        group['source_document_type'] = 'Повернення з сервісу'
            
            return result
        except Exception as e:
            _logger.error(f"Помилка в read_group для stock_serial_report: {e}")
            return []

    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        """Перевизначаємо _search для кращої обробки помилок"""
        try:
            return super()._search(args, offset, limit, order, count, access_rights_uid)
        except Exception as e:
            _logger.error(f"Помилка в _search для stock_serial_report: {e}")
            # Повертаємо порожній результат замість помилки
            return [] if not count else 0
