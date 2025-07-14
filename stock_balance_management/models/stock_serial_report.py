from odoo import models, fields, tools, api
import logging

_logger = logging.getLogger(__name__)

class StockSerialReport(models.Model):
    _name = 'stock.serial.report'
    _description = 'Звіт по серійних номерах'
    _auto = False
    _order = 'nomenclature_name, serial_number'

    # Основні поля
    nomenclature_id = fields.Many2one('product.nomenclature', 'Номенклатура', readonly=True)
    nomenclature_name = fields.Char('Назва товару', readonly=True)
    nomenclature_code = fields.Char('Код товару', readonly=True)
    serial_number = fields.Char('Серійний номер', readonly=True)
    
    # Інформація про локацію
    location_type = fields.Selection([
        ('warehouse', 'Склад'),
        ('employee', 'Працівник'),
    ], 'Тип локації', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', 'Склад', readonly=True)
    warehouse_name = fields.Char('Склад', readonly=True)
    employee_id = fields.Many2one('hr.employee', 'Працівник', readonly=True)
    employee_name = fields.Char('Працівник', readonly=True)
    
    # Партійна інформація
    batch_id = fields.Many2one('stock.batch', 'Партія', readonly=True)
    batch_number = fields.Char('Номер партії', readonly=True)
    
    # Інформація про документ походження
    document_reference = fields.Char('Документ', readonly=True)
    source_document_type = fields.Selection([
        ('receipt', 'Прихідна накладна'),
        ('inventory', 'Акт оприходування'),
        ('return', 'Повернення з сервісу'),
        ('adjustment', 'Коригування'),
        ('transfer', 'Переміщення'),
    ], 'Тип документу', readonly=True)
    source_document_display = fields.Char('Тип документу (відображення)', readonly=True)
    
    # Дати
    date_created = fields.Datetime('Дата створення партії', readonly=True)
    expiry_date = fields.Date('Дата закінчення терміну', readonly=True)
    last_movement_date = fields.Datetime('Остання операція', readonly=True)
    
    # Компанія та кількості
    company_id = fields.Many2one('res.company', 'Компанія', readonly=True)
    company_name = fields.Char('Компанія', readonly=True)
    qty_available = fields.Float('Доступна кількість', readonly=True)
    qty_on_hand = fields.Float('Фізична кількість', readonly=True)
    
    # Статус партії
    batch_state = fields.Selection([
        ('active', 'Активна'),
        ('depleted', 'Вичерпана'),
        ('expired', 'Прострочена'),
        ('blocked', 'Заблокована'),
    ], 'Статус партії', readonly=True)
    
    # Додаткові поля для кращого відображення
    location_full_name = fields.Char('Повна назва локації', readonly=True)
    category_name = fields.Char('Категорія товару', readonly=True)
    tracking_info = fields.Char('Інформація відстеження', readonly=True)

    def init(self):
        """Створює SQL view для звіту серійних номерів"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        
        query = """
            CREATE OR REPLACE VIEW %s AS (
                SELECT 
                    row_number() OVER (ORDER BY pn.name, serial_data.serial_number) AS id,
                    
                    -- Основна інформація про товар
                    sb.nomenclature_id,
                    pn.name AS nomenclature_name,
                    pn.code AS nomenclature_code,
                    serial_data.serial_number,
                    
                    -- Категорія товару
                    pc.name AS category_name,
                    
                    -- Локація
                    sb.location_type,
                    sb.warehouse_id,
                    sw.name AS warehouse_name,
                    sb.employee_id,
                    he.name AS employee_name,
                    
                    -- Повна назва локації
                    CASE 
                        WHEN sb.location_type = 'warehouse' THEN CONCAT('Склад: ', COALESCE(sw.name, 'Невідомий'))
                        WHEN sb.location_type = 'employee' THEN CONCAT('Працівник: ', COALESCE(he.name, 'Невідомий'))
                        ELSE 'Невідома локація'
                    END AS location_full_name,
                    
                    -- Партія
                    sb.batch_id,
                    COALESCE(batch.batch_number, '') AS batch_number,
                    batch.state AS batch_state,
                    
                    -- Документ походження
                    COALESCE(batch.source_document_number, '') AS document_reference,
                    batch.source_document_type,
                    CASE 
                        WHEN batch.source_document_type = 'receipt' THEN 'Прихідна накладна'
                        WHEN batch.source_document_type = 'inventory' THEN 'Акт оприходування'
                        WHEN batch.source_document_type = 'return' THEN 'Повернення з сервісу'
                        WHEN batch.source_document_type = 'adjustment' THEN 'Коригування'
                        WHEN batch.source_document_type = 'transfer' THEN 'Переміщення'
                        ELSE COALESCE(batch.source_document_type, 'Невідомо')
                    END AS source_document_display,
                    
                    -- Дати
                    batch.date_created,
                    batch.expiry_date,
                    
                    -- Остання операція (з рухів залишків)
                    (SELECT MAX(sbm.date) 
                     FROM stock_balance_movement sbm 
                     WHERE sbm.nomenclature_id = sb.nomenclature_id 
                       AND sbm.batch_id = sb.batch_id
                       AND sbm.serial_numbers LIKE '%%' || serial_data.serial_number || '%%'
                    ) AS last_movement_date,
                    
                    -- Компанія
                    sb.company_id,
                    rc.name AS company_name,
                    
                    -- Кількості
                    sb.qty_available,
                    sb.qty_on_hand,
                    
                    -- Інформація відстеження
                    CONCAT(
                        'S/N: ', serial_data.serial_number,
                        CASE WHEN batch.batch_number IS NOT NULL 
                             THEN CONCAT(' | Партія: ', batch.batch_number) 
                             ELSE '' END,
                        CASE WHEN batch.source_document_number IS NOT NULL 
                             THEN CONCAT(' | Док: ', batch.source_document_number) 
                             ELSE '' END
                    ) AS tracking_info
                    
                FROM stock_balance sb
                
                -- Підключаємо номенклатуру
                LEFT JOIN product_nomenclature pn ON pn.id = sb.nomenclature_id
                LEFT JOIN product_nomenclature_category pc ON pc.id = pn.category_id
                
                -- Підключаємо локації
                LEFT JOIN stock_warehouse sw ON sw.id = sb.warehouse_id
                LEFT JOIN hr_employee he ON he.id = sb.employee_id
                
                -- Підключаємо партії
                LEFT JOIN stock_batch batch ON batch.id = sb.batch_id
                
                -- Підключаємо компанію
                LEFT JOIN res_company rc ON rc.id = sb.company_id
                
                -- Розбиваємо серійні номери
                CROSS JOIN LATERAL (
                    SELECT trim(serial) AS serial_number
                    FROM unnest(
                        string_to_array(
                            replace(replace(sb.serial_numbers, E'\\n', ','), E'\\r', ','), 
                            ','
                        )
                    ) AS serial
                    WHERE trim(serial) != '' AND trim(serial) IS NOT NULL
                ) AS serial_data
                
                WHERE sb.serial_numbers IS NOT NULL
                  AND sb.serial_numbers != ''
                  AND trim(sb.serial_numbers) != ''
                  AND sb.qty_available > 0
                  
                ORDER BY pn.name, serial_data.serial_number
            )
        """ % self._table

        self.env.cr.execute(query)
        _logger.info("Створено SQL view для звіту серійних номерів")

    def action_view_balance_details(self):
        """Відкриває детальну інформацію про залишок"""
        self.ensure_one()
        
        # Знаходимо відповідний залишок
        domain = [
            ('nomenclature_id', '=', self.nomenclature_id.id),
            ('location_type', '=', self.location_type),
        ]
        
        if self.location_type == 'warehouse':
            domain.append(('warehouse_id', '=', self.warehouse_id.id))
        else:
            domain.append(('employee_id', '=', self.employee_id.id))
        
        if self.batch_id:
            domain.append(('batch_id', '=', self.batch_id.id))
        
        balance = self.env['stock.balance'].search(domain, limit=1)
        
        if balance:
            return {
                'name': f'Залишок: {self.nomenclature_name}',
                'type': 'ir.actions.act_window',
                'res_model': 'stock.balance',
                'res_id': balance.id,
                'view_mode': 'form',
                'target': 'new',
            }
        else:
            from odoo.exceptions import UserError
            raise UserError('Залишок не знайдено')

    def action_view_batch_details(self):
        """Відкриває детальну інформацію про партію"""
        self.ensure_one()
        
        if not self.batch_id:
            from odoo.exceptions import UserError
            raise UserError('Для цього серійного номера немає партії')
        
        return {
            'name': f'Партія: {self.batch_number}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.batch',
            'res_id': self.batch_id.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_view_movements_history(self):
        """Показує історію рухів для цього серійного номера"""
        self.ensure_one()
        
        # Шукаємо рухи що містять цей серійний номер
        domain = [
            ('nomenclature_id', '=', self.nomenclature_id.id),
            ('serial_numbers', 'ilike', self.serial_number),
        ]
        
        if self.batch_id:
            domain.append(('batch_id', '=', self.batch_id.id))
        
        return {
            'name': f'Історія рухів S/N: {self.serial_number}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.balance.movement',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'search_default_group_date': 1,
            }
        }