from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SerialTrackingMixin(models.AbstractModel):
    """Міксин для роботи з серійними номерами"""
    _name = 'serial.tracking.mixin'
    _description = 'Міксин для відстеження серійних номерів'

    has_serial_products = fields.Boolean(
        'Є товари з S/N',
        compute='_compute_has_serial_products',
        help='Чи є в документі товари з обліком по серійних номерах'
    )
    
    @api.depends('line_ids.nomenclature_id.tracking_serial')
    def _compute_has_serial_products(self):
        """Перевіряє чи є товари з обліком по серійних номерах"""
        for record in self:
            record.has_serial_products = any(
                line.nomenclature_id.tracking_serial for line in record.line_ids
            )
    
    def action_input_serial_numbers(self):
        """Універсальний метод для введення серійних номерів"""
        if not self.has_serial_products:
            raise UserError(_('У документі немає товарів з обліком по серійних номерах!'))
        
        return {
            'name': _('Введення серійних номерів'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.serial.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_model': self._name,
                'default_document_id': self.id,
            }
        }
    
    def _create_serial_numbers(self, posting_datetime=None):
        """Створює записи серійних номерів в централізованій таблиці
        
        Args:
            posting_datetime: Час проведення документа
        """
        SerialNumber = self.env['stock.serial.number']
        
        for line in self.line_ids.filtered('nomenclature_id.tracking_serial'):
            if not line.serial_numbers:
                continue
            
            document_type = self._get_document_type_for_serials()
            
            location_type, warehouse_id, employee_id = self._get_default_location_for_serials()
            
            SerialNumber.create_from_text(
                serial_text=line.serial_numbers,
                nomenclature_id=line.nomenclature_id.id,
                document_type=document_type,
                document_id=self.id,
                document_reference=self.number,
                location_type=location_type,
                warehouse_id=warehouse_id,
                employee_id=employee_id,
                company_id=self.company_id.id,
                notes=f"Створено з документа {self.number} від {self.date}"
            )
    
    def _get_document_type_for_serials(self):
        """Визначає тип документа для серійних номерів
        
        Має бути перевизначений в дочірніх класах
        """
        if 'incoming' in self._name:
            return 'incoming'
        elif 'disposal' in self._name:
            return 'disposal'
        elif 'return' in self._name:
            return 'return'
        else:
            return 'incoming'  # За замовчуванням
    
    def _get_default_location_for_serials(self):
        """Визначає локацію за замовчуванням для серійних номерів
        
        Returns:
            tuple: (location_type, warehouse_id, employee_id)
        """
        return ('warehouse', self.warehouse_id.id if self.warehouse_id else None, None)
    
    def _update_serial_numbers_location(self, new_location_type, warehouse_id=None, employee_id=None):
        """Оновлює локацію серійних номерів документа
        
        Args:
            new_location_type (str): Новий тип локації
            warehouse_id (int, optional): ID складу
            employee_id (int, optional): ID працівника
        """
        SerialNumber = self.env['stock.serial.number']
        
        serials = SerialNumber.search([
            ('document_type', '=', self._get_document_type_for_serials()),
            ('document_id', '=', self.id),
            ('is_active', '=', True)
        ])
        
        if serials:
            serials.update_location(
                location_type=new_location_type,
                warehouse_id=warehouse_id,
                employee_id=employee_id,
                notes=f"Оновлено з документа {self.number}"
            )
    
    def _validate_serial_numbers_uniqueness(self):
        """Перевіряє унікальність серійних номерів перед створенням"""
        SerialNumber = self.env['stock.serial.number']
        
        for line in self.line_ids.filtered('nomenclature_id.tracking_serial'):
            if not line.serial_numbers:
                continue
            
            serials = SerialNumber._parse_serial_text(line.serial_numbers)
            for serial in serials:
                existing = SerialNumber.search([
                    ('serial_number', '=', serial),
                    ('nomenclature_id', '=', line.nomenclature_id.id),
                    ('company_id', '=', self.company_id.id),
                    ('is_active', '=', True)
                ])
                
                if existing:
                    raise UserError(
                        _('Серійний номер "%s" вже існує в системі для товару "%s"!\n'
                          'Поточна локація: %s') % 
                        (serial, line.nomenclature_id.name, existing.display_location)
                    )
    
    def action_view_serial_numbers(self):
        """Показує серійні номери документа"""
        SerialNumber = self.env['stock.serial.number']
        
        serials = SerialNumber.search([
            ('document_type', '=', self._get_document_type_for_serials()),
            ('document_id', '=', self.id)
        ])
        
        return {
            'name': _('Серійні номери документа %s') % self.number,
            'type': 'ir.actions.act_window',
            'res_model': 'stock.serial.number',
            'view_mode': 'list,form',
            'domain': [('id', 'in', serials.ids)],
            'context': {'create': False},
        }
