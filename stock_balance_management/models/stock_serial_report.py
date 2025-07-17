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

        # Тимчасово відключаємо ініціалізацію через помилки з JSON
        _logger.warning("Ініціалізація stock_serial_report тимчасово відключена")
        try:
            # Створюємо порожню view як fallback
            self.env.cr.execute("""
                CREATE OR REPLACE VIEW %s AS (
                    SELECT 
                        1 AS id,
                        NULL::integer AS nomenclature_id,
                        'Сервіс недоступний'::varchar AS nomenclature_name,
                        'Сервіс недоступний'::varchar AS serial_number,
                        'warehouse'::varchar AS location_type,
                        'Сервіс недоступний'::varchar AS warehouse_name,
                        'Сервіс недоступний'::varchar AS employee_name,
                        'Сервіс недоступний'::varchar AS batch_number,
                        'Сервіс недоступний'::varchar AS document_reference,
                        'Сервіс недоступний'::varchar AS source_document_type,
                        1::integer AS company_id,
                        0::float AS qty_available
                    WHERE FALSE
                )
            """ % self._table)
        except Exception as e:
            _logger.error(f"Навіть fallback view не створився: {e}")
            
        return
        
        try:
            # Створюємо view з безпечною обробкою помилок
            # Створюємо максимально простий SQL view
            sql_query = """
                CREATE OR REPLACE VIEW {} AS (
                    SELECT 
                        sb.id,
                        sb.nomenclature_id,
                        sb.serial_numbers AS nomenclature_name,
                        sb.serial_numbers AS serial_number,
                        sb.location_type,
                        'N/A' AS warehouse_name,
                        'N/A' AS employee_name,
                        'N/A' AS batch_number,
                        'N/A' AS document_reference,
                        'N/A' AS source_document_type,
                        sb.company_id,
                        sb.qty_available
                    FROM stock_balance sb
                    WHERE sb.serial_numbers IS NOT NULL
                    AND sb.serial_numbers != ''
                    AND sb.qty_available > 0
                    ORDER BY sb.id
                )
            """.format(self._table)
            
            self.env.cr.execute(sql_query)
            
        except Exception as e:
            _logger.error(f"Помилка створення view stock_serial_report: {e}")
            
            # Rollback транзакції та спробуємо знову
            self.env.cr.rollback()
            
            # Спробуємо створити view без JOIN
            try:
                self.env.cr.execute("""
                    CREATE OR REPLACE VIEW %s AS (
                        SELECT 
                            sb.id,
                            sb.nomenclature_id,
                            sb.serial_numbers AS nomenclature_name,
                            sb.serial_numbers AS serial_number,
                            sb.location_type,
                            'Warehouse' AS warehouse_name,
                            'Employee' AS employee_name,
                            'Batch' AS batch_number,
                            'Document' AS document_reference,
                            'Type' AS source_document_type,
                            sb.company_id,
                            sb.qty_available
                        FROM stock_balance sb
                        WHERE sb.serial_numbers IS NOT NULL
                        AND sb.serial_numbers != ''
                        AND sb.qty_available > 0
                    )
                """ % self._table)
            except Exception as e2:
                _logger.error(f"Помилка створення спрощеного view: {e2}")
                
                # Rollback транзакції та створюємо порожню view як fallback
                self.env.cr.rollback()
                
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
        """Перевизначаємо search_read для обробки NULL значень та перекладів"""
        try:
            result = super().search_read(domain, fields, offset, limit, order)
            
            # Обробляємо NULL значення та додаємо переклади
            for record in result:
                # Обробка nomenclature_name
                if 'nomenclature_name' in record and not record['nomenclature_name']:
                    record['nomenclature_name'] = 'Невідомий товар'
                
                # Обробка warehouse_name
                if 'warehouse_name' in record and not record['warehouse_name']:
                    record['warehouse_name'] = ''
                
                # Обробка employee_name  
                if 'employee_name' in record and not record['employee_name']:
                    record['employee_name'] = ''
                
                # Обробка batch_number
                if 'batch_number' in record and not record['batch_number']:
                    record['batch_number'] = ''
                
                # Обробка document_reference
                if 'document_reference' in record and not record['document_reference']:
                    record['document_reference'] = ''
                
                # Переклад source_document_type
                if 'source_document_type' in record:
                    doc_type = record['source_document_type']
                    if doc_type == 'receipt':
                        record['source_document_type'] = 'Прихідна накладна'
                    elif doc_type == 'inventory':
                        record['source_document_type'] = 'Акт оприходування'
                    elif doc_type == 'return':
                        record['source_document_type'] = 'Повернення з сервісу'
                    elif not doc_type:
                        record['source_document_type'] = ''
            
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
                    doc_type = group['source_document_type']
                    if doc_type == 'receipt':
                        group['source_document_type'] = 'Прихідна накладна'
                    elif doc_type == 'inventory':
                        group['source_document_type'] = 'Акт оприходування'  
                    elif doc_type == 'return':
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