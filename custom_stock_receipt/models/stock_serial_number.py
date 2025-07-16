from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class StockSerialNumber(models.Model):
    _name = 'stock.serial.number'
    _description = 'Серійні номери товарів'
    _rec_name = 'serial_number'
    _order = 'date_created desc, serial_number'

    serial_number = fields.Char(
        'Серійний номер', 
        required=True, 
        index=True,
        help='Унікальний серійний номер товару'
    )
    
    nomenclature_id = fields.Many2one(
        'product.nomenclature', 
        'Товар', 
        required=True, 
        index=True,
        help='Товар до якого належить серійний номер'
    )
    
    document_type = fields.Selection([
        ('incoming', 'Прихідна накладна'),
        ('disposal', 'Акт оприходування'),
        ('return', 'Повернення з сервісу'),
        ('transfer', 'Переміщення'),
        ('inventory', 'Інвентаризація')
    ], 'Тип документу', required=True, index=True)
    
    document_id = fields.Integer(
        'ID документу', 
        required=True, 
        index=True,
        help='ID документу в якому був створений/оновлений серійний номер'
    )
    
    document_reference = fields.Char(
        'Номер документу', 
        index=True,
        help='Номер документу для швидкого пошуку'
    )
    
    current_location_type = fields.Selection([
        ('warehouse', 'Склад'),
        ('employee', 'Працівник'),
        ('service', 'В сервісі'),
        ('disposed', 'Списано')
    ], 'Тип локації', required=True, index=True, default='warehouse')
    
    warehouse_id = fields.Many2one(
        'stock.warehouse', 
        'Склад',
        help='Склад де зараз знаходиться товар'
    )
    
    employee_id = fields.Many2one(
        'hr.employee', 
        'Працівник',
        help='Працівник у якого зараз знаходиться товар'
    )
    
    company_id = fields.Many2one(
        'res.company', 
        'Компанія', 
        required=True, 
        index=True,
        default=lambda self: self.env.company
    )
    
    date_created = fields.Datetime(
        'Дата створення', 
        default=fields.Datetime.now, 
        required=True,
        help='Коли серійний номер був вперше зареєстрований в системі'
    )
    
    date_updated = fields.Datetime(
        'Дата оновлення', 
        default=fields.Datetime.now,
        help='Коли останній раз оновлювалась інформація про серійний номер'
    )
    
    is_active = fields.Boolean(
        'Активний', 
        default=True, 
        index=True,
        help='Чи активний серійний номер (не списаний)'
    )
    
    notes = fields.Text(
        'Примітки',
        help='Додаткова інформація про серійний номер'
    )
    
    display_location = fields.Char(
        'Поточна локація',
        compute='_compute_display_location',
        store=True,
        help='Текстове представлення поточної локації'
    )
    
    _sql_constraints = [
        ('unique_serial_nomenclature_active', 
         'UNIQUE(serial_number, nomenclature_id, company_id) WHERE is_active=true',
         'Серійний номер має бути унікальним для товару в межах компанії!'),
    ]
    
    @api.depends('current_location_type', 'warehouse_id', 'employee_id')
    def _compute_display_location(self):
        """Обчислює текстове представлення локації"""
        for record in self:
            if record.current_location_type == 'warehouse' and record.warehouse_id:
                record.display_location = f"Склад: {record.warehouse_id.name}"
            elif record.current_location_type == 'employee' and record.employee_id:
                record.display_location = f"Працівник: {record.employee_id.name}"
            elif record.current_location_type == 'service':
                record.display_location = "В сервісі"
            elif record.current_location_type == 'disposed':
                record.display_location = "Списано"
            else:
                record.display_location = "Невідома локація"
    
    @api.model
    def create_from_text(self, serial_text, nomenclature_id, document_type, document_id, 
                        document_reference, location_type, warehouse_id=None, employee_id=None, 
                        company_id=None, notes=None):
        """Створює записи серійних номерів з текстового поля
        
        Args:
            serial_text (str): Текст з серійними номерами (розділені комами або новими рядками)
            nomenclature_id (int): ID товару
            document_type (str): Тип документу
            document_id (int): ID документу
            document_reference (str): Номер документу
            location_type (str): Тип локації
            warehouse_id (int, optional): ID складу
            employee_id (int, optional): ID працівника
            company_id (int, optional): ID компанії
            notes (str, optional): Примітки
            
        Returns:
            recordset: Створені записи серійних номерів
        """
        if not serial_text or not nomenclature_id:
            return self.env['stock.serial.number']
        
        company_id = company_id or self.env.company.id
        serials = self._parse_serial_text(serial_text)
        created_records = self.env['stock.serial.number']
        
        for serial in serials:
            # Перевірка на дублікати
            existing = self.search([
                ('serial_number', '=', serial),
                ('nomenclature_id', '=', nomenclature_id),
                ('company_id', '=', company_id),
                ('is_active', '=', True)
            ])
            
            if existing:
                raise ValidationError(
                    f'Серійний номер "{serial}" вже існує в системі для товару '
                    f'"{self.env["product.nomenclature"].browse(nomenclature_id).name}"!\n'
                    f'Поточна локація: {existing.display_location}'
                )
            
            record = self.create({
                'serial_number': serial,
                'nomenclature_id': nomenclature_id,
                'document_type': document_type,
                'document_id': document_id,
                'document_reference': document_reference,
                'current_location_type': location_type,
                'warehouse_id': warehouse_id,
                'employee_id': employee_id,
                'company_id': company_id,
                'notes': notes,
            })
            created_records |= record
        
        _logger.info(f"Створено {len(created_records)} серійних номерів для документу {document_reference}")
        return created_records
    
    @api.model
    def _parse_serial_text(self, serial_text):
        """Парсить текст серійних номерів
        
        Args:
            serial_text (str): Текст з серійними номерами
            
        Returns:
            list: Список унікальних серійних номерів
        """
        if not serial_text:
            return []
        
        serials = []
        for line in serial_text.split('\n'):
            for serial in line.split(','):
                serial = serial.strip()
                if serial and serial not in serials:  # Уникаємо дублікатів
                    serials.append(serial)
        return serials
    
    def update_location(self, location_type, warehouse_id=None, employee_id=None, notes=None):
        """Оновлює локацію серійного номера
        
        Args:
            location_type (str): Новий тип локації
            warehouse_id (int, optional): ID нового складу
            employee_id (int, optional): ID нового працівника
            notes (str, optional): Додаткові примітки
        """
        for record in self:
            vals = {
                'current_location_type': location_type,
                'warehouse_id': warehouse_id,
                'employee_id': employee_id,
                'date_updated': fields.Datetime.now()
            }
            
            if notes:
                existing_notes = record.notes or ''
                timestamp = fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                new_note = f"[{timestamp}] {notes}"
                vals['notes'] = f"{existing_notes}\n{new_note}" if existing_notes else new_note
            
            record.write(vals)
        
        _logger.info(f"Оновлено локацію для {len(self)} серійних номерів: {location_type}")
    
    def action_view_history(self):
        """Показує історію переміщень серійного номера"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Історія серійного номера: {self.serial_number}',
            'res_model': 'stock.serial.number',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    @api.model
    def search_by_serial(self, serial_number, company_id=None):
        """Пошук серійного номера в системі
        
        Args:
            serial_number (str): Серійний номер для пошуку
            company_id (int, optional): ID компанії для пошуку
            
        Returns:
            recordset: Знайдені записи
        """
        domain = [
            ('serial_number', '=', serial_number),
            ('is_active', '=', True)
        ]
        
        if company_id:
            domain.append(('company_id', '=', company_id))
        
        return self.search(domain)
    
    @api.model
    def get_available_serials(self, nomenclature_id, location_type, warehouse_id=None, employee_id=None, company_id=None):
        """Отримує доступні серійні номери для товару в локації
        
        Args:
            nomenclature_id (int): ID товару
            location_type (str): Тип локації
            warehouse_id (int, optional): ID складу
            employee_id (int, optional): ID працівника
            company_id (int, optional): ID компанії
            
        Returns:
            recordset: Доступні серійні номери
        """
        domain = [
            ('nomenclature_id', '=', nomenclature_id),
            ('current_location_type', '=', location_type),
            ('is_active', '=', True)
        ]
        
        if warehouse_id:
            domain.append(('warehouse_id', '=', warehouse_id))
        
        if employee_id:
            domain.append(('employee_id', '=', employee_id))
        
        if company_id:
            domain.append(('company_id', '=', company_id))
        else:
            domain.append(('company_id', '=', self.env.company.id))
        
        return self.search(domain)
    
    def write(self, vals):
        """Оновлює дату модифікації при зміні"""
        if any(key in vals for key in ['current_location_type', 'warehouse_id', 'employee_id']):
            vals['date_updated'] = fields.Datetime.now()
        
        return super().write(vals)
    
    def name_get(self):
        """Кастомне відображення назви"""
        result = []
        for record in self:
            name = f"{record.serial_number} ({record.nomenclature_id.name})"
            result.append((record.id, name))
        return result
