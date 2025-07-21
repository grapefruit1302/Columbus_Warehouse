from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, date
import logging

_logger = logging.getLogger(__name__)

class StockBalanceRegister(models.Model):
    """
    Регістр накопичення залишків товарів за архітектурою 1С
    
    Аналог РегистрНакопления "ТоварыНаСкладах" з 1С:
    - Виміри (Измерения): номенклатура, склад, локація, партія, серійний номер, організація
    - Ресурси (Ресурсы): кількість  
    - Реквізити (Реквизиты): тип операції, документ-джерело
    """
    _name = 'stock.balance.register'
    _description = 'Регістр накопичення залишків товарів'
    _order = 'period desc, id desc'
    _rec_name = 'display_name'

    # ========== ПЕРІОД ==========
    period = fields.Datetime(
        'Період', 
        required=True,
        default=fields.Datetime.now,
        index=True,
        help='Дата та час регістрації руху'
    )

    # ========== ВИМІРИ (Измерения) ==========
    nomenclature_id = fields.Many2one(
        'product.nomenclature', 
        'Номенклатура', 
        required=True,
        index=True,
        help='Вимір: номенклатура товару'
    )
    
    warehouse_id = fields.Many2one(
        'stock.warehouse', 
        'Склад',
        index=True,
        help='Вимір: склад'
    )
    
    location_id = fields.Many2one(
        'stock.location', 
        'Локація',
        index=True, 
        help='Вимір: конкретна локація на складі'
    )
    
    batch_number = fields.Char(
        'Партія',
        index=True,
        help='Вимір: номер партії товару'
    )
    
    serial_number = fields.Char(
        'Серійний номер',
        index=True,
        help='Вимір: серійний номер товару'
    )
    
    employee_id = fields.Many2one(
        'hr.employee', 
        'Працівник',
        index=True,
        help='Вимір: працівник (для підзвітних товарів)'
    )
    
    company_id = fields.Many2one(
        'res.company', 
        'Організація', 
        required=True,
        default=lambda self: self.env.company,
        index=True,
        help='Вимір: організація'
    )

    # ========== РЕСУРСИ (Ресурсы) ==========
    quantity = fields.Float(
        'Кількість',
        digits='Product Unit of Measure',
        help='Ресурс: кількість товару (може бути від\'ємна для списання)'
    )
    
    uom_id = fields.Many2one(
        'uom.uom', 
        'Од. виміру', 
        required=True,
        help='Одиниця виміру кількості'
    )

    # ========== РЕКВІЗИТИ (Реквизиты) ==========
    operation_type = fields.Selection([
        ('receipt', 'Надходження'),
        ('disposal', 'Списання'),
        ('transfer', 'Переміщення'),
        ('inventory', 'Інвентаризація'),
        ('adjustment', 'Коригування'),
        ('return', 'Повернення'),
    ], 'Тип операції', required=True, help='Реквізит: тип операції')
    
    document_reference = fields.Char(
        'Документ',
        help='Реквізит: посилання на документ-джерело'
    )
    
    recorder_type = fields.Char(
        'Тип документа',
        help='Реквізит: тип документа що створив запис'
    )
    
    recorder_id = fields.Integer(
        'ID документа',
        help='Реквізит: ID документа що створив запис'
    )

    # ========== СЛУЖБОВІ ПОЛЯ ==========
    active = fields.Boolean(
        'Активний', 
        default=True,
        help='Ознака активності запису'
    )
    
    notes = fields.Text(
        'Примітки',
        help='Додаткові примітки до запису'
    )
    
    display_name = fields.Char(
        'Назва',
        compute='_compute_display_name',
        store=True
    )

    # ========== ІНДЕКСИ та ОБМЕЖЕННЯ ==========
    _sql_constraints = [
        ('check_quantity_uom', 
         'CHECK(quantity IS NOT NULL AND uom_id IS NOT NULL)', 
         'Кількість та одиниця виміру обов\'язкові!'),
        ('check_location_consistency',
         'CHECK((warehouse_id IS NOT NULL AND employee_id IS NULL) OR '
               '(employee_id IS NOT NULL AND warehouse_id IS NULL) OR '
               '(warehouse_id IS NULL AND employee_id IS NULL))',
         'Може бути вказаний або склад, або працівник, але не обидва!')
    ]

    @api.depends('nomenclature_id', 'warehouse_id', 'location_id', 'employee_id', 'batch_number', 'quantity', 'operation_type')
    def _compute_display_name(self):
        """Обчислює відображувану назву запису"""
        for record in self:
            parts = []
            
            if record.nomenclature_id:
                parts.append(record.nomenclature_id.name)
            
            if record.warehouse_id:
                parts.append(f"Склад: {record.warehouse_id.name}")
            elif record.employee_id:
                parts.append(f"Працівник: {record.employee_id.name}")
            
            if record.batch_number:
                parts.append(f"Партія: {record.batch_number}")
            
            if record.quantity:
                sign = "+" if record.quantity > 0 else ""
                parts.append(f"{sign}{record.quantity}")
            
            record.display_name = " | ".join(parts)

    # ========== МЕТОДИ РОБОТИ З РЕГІСТРОМ (як в 1С) ==========

    @api.model
    def get_balance(self, period=None, dimensions=None):
        """
        Отримати залишок на дату (як в 1С)
        
        Args:
            period (datetime): дата на яку отримати залишок
            dimensions (dict): виміри для фільтрації
                - nomenclature_id: ID номенклатури  
                - warehouse_id: ID складу
                - location_id: ID локації
                - batch_number: номер партії
                - serial_number: серійний номер
                - employee_id: ID працівника
                - company_id: ID компанії
        
        Returns:
            float: залишок на дату
        """
        if period is None:
            period = fields.Datetime.now()
        
        domain = [
            ('period', '<=', period),
            ('active', '=', True)
        ]
        
        if dimensions:
            for dim_key, dim_value in dimensions.items():
                if dim_value is not None:
                    domain.append((dim_key, '=', dim_value))
        
        records = self.search(domain)
        total_balance = sum(record.quantity for record in records)
        
        return total_balance

    @api.model
    def get_turnovers(self, period_from, period_to, dimensions=None):
        """
        Отримати обороти за період (як в 1С)
        
        Args:
            period_from (datetime): дата початку періоду
            period_to (datetime): дата закінчення періоду  
            dimensions (dict): виміри для фільтрації
            
        Returns:
            dict: {'receipt': float, 'disposal': float, 'turnover': float}
        """
        domain = [
            ('period', '>=', period_from),
            ('period', '<=', period_to),
            ('active', '=', True)
        ]
        
        if dimensions:
            for dim_key, dim_value in dimensions.items():
                if dim_value is not None:
                    domain.append((dim_key, '=', dim_value))
        
        records = self.search(domain)
        
        receipt = sum(record.quantity for record in records if record.quantity > 0)
        disposal = sum(abs(record.quantity) for record in records if record.quantity < 0)
        turnover = receipt - disposal
        
        return {
            'receipt': receipt,
            'disposal': disposal, 
            'turnover': turnover
        }

    @api.model
    def write_record(self, dimensions, resources, attributes):
        """
        Записати рух в регістр (як в 1С)
        
        Args:
            dimensions (dict): виміри
            resources (dict): ресурси  
            attributes (dict): реквізити
            
        Returns:
            stock.balance.register: створений запис
        """
        vals = {}
        vals.update(dimensions)
        vals.update(resources)
        vals.update(attributes)
        
        # Встановлюємо період якщо не вказаний
        if 'period' not in vals:
            vals['period'] = fields.Datetime.now()
            
        return self.create(vals)

    @api.model
    def delete_records(self, recorder_type, recorder_id):
        """
        Видалити записи документа (як в 1С при скасуванні проведення)
        
        Args:
            recorder_type (str): тип документа
            recorder_id (int): ID документа
        """
        domain = [
            ('recorder_type', '=', recorder_type),
            ('recorder_id', '=', recorder_id)
        ]
        
        records = self.search(domain)
        records.unlink()
        
        _logger.info(f"Видалено {len(records)} записів регістра для документа {recorder_type}:{recorder_id}")

    @api.model
    def fifo_consumption(self, nomenclature_id, quantity, location_dimensions=None, company_id=None):
        """
        Списання за FIFO логікою (як в 1С)
        
        Args:
            nomenclature_id (int): ID номенклатури
            quantity (float): кількість для списання
            location_dimensions (dict): додаткові локаційні виміри
            company_id (int): ID компанії
            
        Returns:
            list: список партій для списання з кількостями
        """
        if company_id is None:
            company_id = self.env.company.id
            
        # Отримуємо залишки по партіях за FIFO
        fifo_query = """
            SELECT 
                batch_number,
                serial_number,
                SUM(quantity) as balance,
                MIN(period) as first_receipt_date
            FROM stock_balance_register 
            WHERE nomenclature_id = %s 
                AND company_id = %s
                AND active = true
        """
        
        params = [nomenclature_id, company_id]
        
        if location_dimensions:
            if location_dimensions.get('warehouse_id'):
                fifo_query += " AND warehouse_id = %s"
                params.append(location_dimensions['warehouse_id'])
            if location_dimensions.get('employee_id'):
                fifo_query += " AND employee_id = %s"
                params.append(location_dimensions['employee_id'])
        
        fifo_query += """
            GROUP BY batch_number, serial_number
            HAVING SUM(quantity) > 0
            ORDER BY MIN(period) ASC
        """
        
        self.env.cr.execute(fifo_query, params)
        fifo_batches = self.env.cr.fetchall()
        
        consumption_list = []
        remaining_qty = quantity
        
        for batch_number, serial_number, balance, first_date in fifo_batches:
            if remaining_qty <= 0:
                break
                
            take_qty = min(balance, remaining_qty)
            consumption_list.append({
                'batch_number': batch_number,
                'serial_number': serial_number,
                'quantity': take_qty,
                'balance': balance
            })
            remaining_qty -= take_qty
        
        if remaining_qty > 0:
            raise ValidationError(
                _('Недостатньо залишку для списання. Потрібно: %s, доступно: %s') % 
                (quantity, quantity - remaining_qty)
            )
        
        return consumption_list

    @api.model
    def create_batch_from_receipt(self, nomenclature_id, quantity, receipt_doc, location_dims, serial_numbers=None):
        """
        Створює партію при надходженні (партія = вимір регістра)
        
        Args:
            nomenclature_id (int): ID номенклатури
            quantity (float): кількість
            receipt_doc (dict): дані документа надходження
            location_dims (dict): локаційні виміри
            serial_numbers (list): список серійних номерів
        """
        nomenclature = self.env['product.nomenclature'].browse(nomenclature_id)
        
        # Генеруємо номер партії
        batch_number = self._generate_batch_number(nomenclature, receipt_doc)
        
        # Перевіряємо чи товар має серійний облік
        if nomenclature.tracking_serial and serial_numbers:
            # Для товарів з серійним обліком створюємо окремі записи для кожного S/N
            for serial in serial_numbers:
                self.write_record(
                    dimensions={
                        'nomenclature_id': nomenclature_id,
                        'batch_number': batch_number,
                        'serial_number': serial,
                        'company_id': self.env.company.id,
                        **location_dims
                    },
                    resources={
                        'quantity': 1.0,  # По 1 штуці для кожного серійного номера
                        'uom_id': nomenclature.base_uom_id.id
                    },
                    attributes={
                        'operation_type': 'receipt',
                        'document_reference': receipt_doc.get('document_reference'),
                        'recorder_type': receipt_doc.get('recorder_type'),
                        'recorder_id': receipt_doc.get('recorder_id'),
                        'period': receipt_doc.get('period', fields.Datetime.now())
                    }
                )
        else:
            # Для звичайних товарів створюємо один запис з загальною кількістю
            self.write_record(
                dimensions={
                    'nomenclature_id': nomenclature_id,
                    'batch_number': batch_number,
                    'company_id': self.env.company.id,
                    **location_dims
                },
                resources={
                    'quantity': quantity,
                    'uom_id': nomenclature.base_uom_id.id
                },
                attributes={
                    'operation_type': 'receipt',
                    'document_reference': receipt_doc.get('document_reference'),
                    'recorder_type': receipt_doc.get('recorder_type'),
                    'recorder_id': receipt_doc.get('recorder_id'),
                    'period': receipt_doc.get('period', fields.Datetime.now())
                }
            )
        
        return batch_number

    def _generate_batch_number(self, nomenclature, receipt_doc):
        """Генерує номер партії"""
        today = fields.Date.today()
        date_str = today.strftime('%d%m%y')
        
        doc_ref = receipt_doc.get('document_reference', 'DOC')
        
        # Формат: НОМЕНКЛАТУРА_ДДММРР_НОМЕРДОК
        batch_number = f"{nomenclature.code or nomenclature.name[:10]}_{date_str}_{doc_ref}"
        
        # Перевіряємо унікальність
        counter = 1
        original_batch = batch_number
        while self.search_count([('batch_number', '=', batch_number)]) > 0:
            batch_number = f"{original_batch}_{counter}"
            counter += 1
        
        return batch_number

    # ========== ЗВІТИ та АНАЛІЗ ==========

    @api.model 
    def get_balance_sheet(self, period=None, group_by=None):
        """
        Оборотно-сальдова відомість (як в 1С)
        
        Args:
            period (datetime): дата на яку формувати
            group_by (list): поля для групування
            
        Returns:
            list: список записів з залишками
        """
        if period is None:
            period = fields.Datetime.now()
            
        if group_by is None:
            group_by = ['nomenclature_id', 'warehouse_id', 'batch_number']
        
        # SQL запит для отримання зведених даних
        group_fields = ', '.join(group_by)
        query = f"""
            SELECT 
                {group_fields},
                SUM(CASE WHEN quantity > 0 THEN quantity ELSE 0 END) as receipt_total,
                SUM(CASE WHEN quantity < 0 THEN ABS(quantity) ELSE 0 END) as disposal_total,
                SUM(quantity) as balance
            FROM stock_balance_register 
            WHERE period <= %s AND active = true
            GROUP BY {group_fields}
            HAVING SUM(quantity) != 0
            ORDER BY {group_by[0]}
        """
        
        self.env.cr.execute(query, [period])
        results = self.env.cr.fetchall()
        
        return results

    def action_view_register_records(self):
        """Відкриває записи регістра для перегляду"""
        return {
            'name': _('Записи регістра накопичення'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.balance.register',
            'view_mode': 'list,form',
            'domain': [],
            'context': {'create': False},
        }