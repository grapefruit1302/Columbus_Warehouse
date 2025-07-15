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
        
        # Перевіряємо, чи існують необхідні таблиці
        self.env.cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'stock_balance'
            )
        """)
        stock_balance_exists = self.env.cr.fetchone()[0]
        
        if not stock_balance_exists:
            _logger.warning("Таблиця stock_balance не існує. Створюємо порожню view.")
            self.env.cr.execute("""
                CREATE OR REPLACE VIEW %s AS (
                    SELECT 
                        1 AS id,
                        NULL::integer AS nomenclature_id,
                        'Немає даних'::varchar AS nomenclature_name,
                        'Немає даних'::varchar AS serial_number,
                        'warehouse'::varchar AS location_type,
                        'Немає даних'::varchar AS warehouse_name,
                        'Немає даних'::varchar AS employee_name,
                        'Немає даних'::varchar AS batch_number,
                        'Немає даних'::varchar AS document_reference,
                        'Немає даних'::varchar AS source_document_type,
                        1::integer AS company_id,
                        0::float AS qty_available
                    WHERE FALSE
                )
            """ % self._table)
            return

        # Перевіряємо, чи існують залежні таблиці
        self.env.cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'product_nomenclature'
            )
        """)
        nomenclature_exists = self.env.cr.fetchone()[0]
        
        if not nomenclature_exists:
            _logger.warning("Таблиця product_nomenclature не існує")
            return

        try:
            # Створюємо view з безпечною обробкою помилок
            self.env.cr.execute("""
                CREATE OR REPLACE VIEW %s AS (
                    WITH serial_data AS (
                        SELECT 
                            sb.id as balance_id,
                            sb.nomenclature_id,
                            sb.location_type,
                            sb.warehouse_id,
                            sb.employee_id,
                            sb.batch_id,
                            sb.company_id,
                            sb.qty_available,
                            trim(serial) AS serial_number
                        FROM stock_balance sb
                        CROSS JOIN LATERAL (
                            SELECT trim(unnest(string_to_array(
                                replace(COALESCE(sb.serial_numbers, ''), E'\n', ','), ','
                            ))) AS serial
                        ) AS serial_split
                        WHERE sb.serial_numbers IS NOT NULL
                        AND sb.serial_numbers != ''
                        AND sb.qty_available > 0
                        AND trim(serial_split.serial) != ''
                    )
                    SELECT 
                        row_number() OVER (ORDER BY pn.name, sd.serial_number) AS id,
                        sd.nomenclature_id,
                        COALESCE(pn.name, 'Невідомий товар') AS nomenclature_name,
                        sd.serial_number,
                        sd.location_type,
                        COALESCE(sw.name, '') AS warehouse_name,
                        COALESCE(he.name, '') AS employee_name,
                        COALESCE(batch.batch_number, '') AS batch_number,
                        COALESCE(batch.source_document_number, '') AS document_reference,
                        CASE 
                            WHEN batch.source_document_type = 'receipt' THEN 'Прихідна накладна'
                            WHEN batch.source_document_type = 'inventory' THEN 'Акт оприходування'
                            WHEN batch.source_document_type = 'return' THEN 'Повернення з сервісу'
                            ELSE COALESCE(batch.source_document_type, '')
                        END AS source_document_type,
                        sd.company_id,
                        sd.qty_available
                    FROM serial_data sd
                    LEFT JOIN product_nomenclature pn ON pn.id = sd.nomenclature_id
                    LEFT JOIN stock_warehouse sw ON sw.id = sd.warehouse_id
                    LEFT JOIN hr_employee he ON he.id = sd.employee_id
                    LEFT JOIN stock_batch batch ON batch.id = sd.batch_id
                    WHERE sd.serial_number IS NOT NULL
                    AND sd.serial_number != ''
                    ORDER BY pn.name, sd.serial_number
                )
            """ % self._table)
            
        except Exception as e:
            _logger.error(f"Помилка створення view stock_serial_report: {e}")
            # Створюємо порожню view як fallback
            self.env.cr.execute("""
                CREATE OR REPLACE VIEW %s AS (
                    SELECT 
                        1 AS id,
                        NULL::integer AS nomenclature_id,
                        'Помилка завантаження даних'::varchar AS nomenclature_name,
                        'Помилка'::varchar AS serial_number,
                        'warehouse'::varchar AS location_type,
                        ''::varchar AS warehouse_name,
                        ''::varchar AS employee_name,
                        ''::varchar AS batch_number,
                        ''::varchar AS document_reference,
                        ''::varchar AS source_document_type,
                        1::integer AS company_id,
                        0::float AS qty_available
                    WHERE FALSE
                )
            """ % self._table)

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """Перевизначаємо search_read для кращої обробки помилок"""
        try:
            return super().search_read(domain, fields, offset, limit, order)
        except Exception as e:
            _logger.error(f"Помилка в search_read для stock_serial_report: {e}")
            # Повертаємо порожній результат замість помилки
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