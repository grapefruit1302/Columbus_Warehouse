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

        # Створюємо view з реальними даними 
        try:
            self.env.cr.execute("""
                CREATE OR REPLACE VIEW %s AS (
                    WITH serial_split AS (
                        SELECT 
                            sb.id,
                            sb.nomenclature_id,
                            sb.location_type,
                            sb.warehouse_id,
                            sb.employee_id,
                            sb.batch_id,
                            sb.company_id,
                            sb.qty_available,
                            TRIM(UNNEST(STRING_TO_ARRAY(sb.serial_numbers, ','))) AS serial_number,
                            ROW_NUMBER() OVER (ORDER BY sb.id) AS row_num
                        FROM stock_balance sb
                        WHERE sb.serial_numbers IS NOT NULL
                        AND sb.serial_numbers != ''
                        AND LENGTH(TRIM(sb.serial_numbers)) > 0
                    )
                    SELECT 
                        (ss.id * 1000 + ss.row_num) AS id,
                        ss.nomenclature_id,
                        'Product Name' AS nomenclature_name,
                        ss.serial_number,
                        ss.location_type,
                        'Warehouse' AS warehouse_name,
                        'Employee' AS employee_name,
                        'Batch' AS batch_number,
                        '' AS document_reference,
                        '' AS source_document_type,
                        ss.company_id,
                        1.0 AS qty_available
                    FROM serial_split ss
                    WHERE ss.serial_number IS NOT NULL
                    AND ss.serial_number != ''
                    AND LENGTH(TRIM(ss.serial_number)) > 0
                )
            """ % self._table)
        except Exception as e:
            _logger.error(f"Помилка створення view з серійними номерами: {e}")
            
            # Fallback до простого view
            self.env.cr.execute("""
                CREATE OR REPLACE VIEW %s AS (
                    SELECT 
                        1 AS id,
                        NULL::integer AS nomenclature_id,
                        'Loading Error'::varchar AS nomenclature_name,
                        'Error'::varchar AS serial_number,
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
            # Спочатку перевіряємо, чи є дані в stock_balance
            self.env.cr.execute("SELECT COUNT(*) FROM stock_balance WHERE serial_numbers IS NOT NULL AND serial_numbers != ''")
            count = self.env.cr.fetchone()[0]
            _logger.info(f"Знайдено {count} записів з серійними номерами в stock_balance")
            
            result = super().search_read(domain, fields, offset, limit, order)
            _logger.info(f"search_read повернув {len(result)} записів")
            
            # Обробляємо NULL значення та додаємо переклади
            for record in result:
                # Отримуємо справжню назву товару
                if 'nomenclature_id' in record and record['nomenclature_id']:
                    try:
                        nomenclature = self.env['product.nomenclature'].browse(record['nomenclature_id'])
                        if nomenclature.exists():
                            # Обробляємо JSON поле name
                            name = nomenclature.name
                            if isinstance(name, dict):
                                # Якщо name - це JSON, беремо значення для української мови
                                record['nomenclature_name'] = name.get('uk_UA', name.get('en_US', str(name)))
                            else:
                                record['nomenclature_name'] = str(name) if name else 'Невідомий товар'
                        else:
                            record['nomenclature_name'] = 'Невідомий товар'
                    except Exception as e:
                        _logger.error(f"Помилка отримання назви товару: {e}")
                        record['nomenclature_name'] = 'Невідомий товар'
                elif 'nomenclature_name' in record:
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
    def web_read(self, ids, fields, specification):
        """Override web_read to prevent _fetch_query errors"""
        try:
            if isinstance(specification, dict):
                field_names = list(specification.keys())
            else:
                field_names = fields or []
            
            if ids:
                records = self.browse(ids)
                result = []
                for record in records:
                    record_data = {'id': record.id}
                    for field in field_names:
                        if hasattr(record, field):
                            record_data[field] = getattr(record, field)
                    result.append(record_data)
                return result
            else:
                return []
        except Exception as e:
            _logger.error(f"Помилка в web_read для stock_serial_report: {e}")
            return []

    @api.model
    def web_search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, count_limit=None):
        """Override web_search_read to use our custom search_read"""
        try:
            records = self.search_read(domain, fields, offset, limit, order)
            return {
                'records': records,
                'length': len(records)
            }
        except Exception as e:
            _logger.error(f"Помилка в web_search_read для stock_serial_report: {e}")
            return {
                'records': [],
                'length': 0
            }

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
        """Simplified _search that avoids query building conflicts"""
        try:
            
            sql = f"SELECT id FROM {self._table}"
            params = []
            
            if args:
                where_conditions = []
                for condition in args:
                    if len(condition) == 3:
                        field, operator, value = condition
                        if operator == '=' and field in ['id', 'nomenclature_id', 'company_id']:
                            where_conditions.append(f"{field} = %s")
                            params.append(value)
                        elif operator == 'ilike' and field in ['nomenclature_name', 'serial_number']:
                            where_conditions.append(f"{field} ILIKE %s")
                            params.append(f'%{value}%')
                
                if where_conditions:
                    sql += " WHERE " + " AND ".join(where_conditions)
            
            if order:
                sql += f" ORDER BY {order}"
            if limit:
                sql += f" LIMIT {limit}"
            if offset:
                sql += f" OFFSET {offset}"
            
            self.env.cr.execute(sql, params)
            
            if count:
                return len(self.env.cr.fetchall())
            else:
                return [row[0] for row in self.env.cr.fetchall()]
                
        except Exception as e:
            _logger.error(f"Помилка в _search для stock_serial_report: {e}")
            return [] if not count else 0

    def read(self, fields=None, load='_classic_read'):
        """Override read to handle _auto = False model properly"""
        try:
            result = []
            for record in self:
                record_data = {'id': record.id}
                if fields:
                    for field in fields:
                        if hasattr(record, field):
                            value = getattr(record, field)
                            if hasattr(value, 'id') and hasattr(value, 'name'):
                                record_data[field] = [value.id, value.name] if value else False
                            else:
                                record_data[field] = value
                        else:
                            record_data[field] = False
                else:
                    for field_name in self._fields:
                        if hasattr(record, field_name):
                            value = getattr(record, field_name)
                            if hasattr(value, 'id') and hasattr(value, 'name'):
                                record_data[field_name] = [value.id, value.name] if value else False
                            else:
                                record_data[field_name] = value
                result.append(record_data)
            return result
        except Exception as e:
            _logger.error(f"Помилка в read для stock_serial_report: {e}")
            return []


