from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class DocumentValidationMixin(models.AbstractModel):
    """Міксин для валідації документів"""
    _name = 'document.validation.mixin'
    _description = 'Міксин для валідації документів'

    def _validate_lines_exist(self):
        """Перевіряє наявність позицій в документі"""
        if not self.line_ids:
            raise UserError(_('Додайте хоча б одну позицію до документа!'))
    
    def _validate_required_fields(self):
        """Перевіряє заповнення обов'язкових полів"""
        errors = []
        
        if not self.warehouse_id:
            errors.append(_('Вкажіть склад'))
        
        if not self.company_id:
            errors.append(_('Вкажіть компанію'))
        
        if not self.date:
            errors.append(_('Вкажіть дату документа'))
        
        if errors:
            raise UserError(_('Помилки валідації:\n%s') % '\n'.join(f'• {error}' for error in errors))
    
    def _validate_serial_numbers(self):
        """Валідація серійних номерів для всіх позицій"""
        errors = []
        
        for line in self.line_ids.filtered('nomenclature_id.tracking_serial'):
            line_errors = self._validate_line_serial_numbers(line)
            if line_errors:
                errors.extend(line_errors)
        
        if errors:
            raise UserError(_('Помилки серійних номерів:\n%s') % '\n'.join(f'• {error}' for error in errors))
    
    def _validate_line_serial_numbers(self, line):
        """Валідація серійних номерів для конкретної позиції
        
        Args:
            line: Позиція документа
            
        Returns:
            list: Список помилок
        """
        errors = []
        
        if not line.serial_numbers:
            errors.append(_('Введіть серійні номери для товару: %s') % line.nomenclature_id.name)
            return errors
        
        serials = self.env['stock.serial.number']._parse_serial_text(line.serial_numbers)
        
        if len(serials) != int(line.qty):
            errors.append(
                _('Кількість серійних номерів (%d) не відповідає кількості товару (%d) для: %s') % 
                (len(serials), line.qty, line.nomenclature_id.name)
            )
        
        if len(serials) != len(set(serials)):
            duplicates = [serial for serial in serials if serials.count(serial) > 1]
            errors.append(
                _('Знайдено дублікати серійних номерів в позиції %s: %s') % 
                (line.nomenclature_id.name, ', '.join(set(duplicates)))
            )
        
        for serial in serials:
            if not self._validate_serial_format(serial):
                errors.append(
                    _('Некоректний формат серійного номера "%s" для товару: %s') % 
                    (serial, line.nomenclature_id.name)
                )
        
        return errors
    
    def _validate_serial_format(self, serial_number):
        """Перевіряє формат серійного номера
        
        Args:
            serial_number (str): Серійний номер для перевірки
            
        Returns:
            bool: True якщо формат коректний
        """
        if not serial_number or not isinstance(serial_number, str):
            return False
        
        if len(serial_number.strip()) < 1:
            return False
        
        forbidden_chars = ['\n', '\r', '\t', '  ']  # Подвійні пробіли також заборонені
        if any(char in serial_number for char in forbidden_chars):
            return False
        
        return True
    
    def _validate_quantities(self):
        """Перевіряє коректність кількостей в позиціях"""
        errors = []
        
        for line in self.line_ids:
            if line.qty <= 0:
                errors.append(
                    _('Кількість має бути більше нуля для товару: %s') % line.nomenclature_id.name
                )
            
            if line.qty > 10000:  # Можна налаштувати
                errors.append(
                    _('Кількість %s занадто велика для товару: %s') % 
                    (line.qty, line.nomenclature_id.name)
                )
        
        if errors:
            raise UserError(_('Помилки кількостей:\n%s') % '\n'.join(f'• {error}' for error in errors))
    
    def _validate_financial_data(self):
        """Перевіряє коректність фінансових даних"""
        errors = []
        
        for line in self.line_ids:
            if line.price_unit_no_vat < 0:
                errors.append(
                    _('Ціна без ПДВ не може бути від\'ємною для товару: %s') % line.nomenclature_id.name
                )
            
            if line.price_unit_with_vat < 0:
                errors.append(
                    _('Ціна з ПДВ не може бути від\'ємною для товару: %s') % line.nomenclature_id.name
                )
            
            if not (0 <= line.vat_rate <= 100):
                errors.append(
                    _('Ставка ПДВ має бути від 0 до 100%% для товару: %s') % line.nomenclature_id.name
                )
        
        if errors:
            raise UserError(_('Помилки фінансових даних:\n%s') % '\n'.join(f'• {error}' for error in errors))
    
    def _validate_before_confirm(self):
        """Комплексна валідація перед підтвердженням"""
        self._validate_lines_exist()
        self._validate_required_fields()
        self._validate_quantities()
        self._validate_financial_data()
    
    def _validate_before_posting(self):
        """Комплексна валідація перед проведенням"""
        self._validate_before_confirm()
        self._validate_serial_numbers()
        
        if self.state != 'confirmed':
            raise UserError(_('Документ має бути підтверджений перед проведенням!'))
    
    def _validate_warehouse_access(self):
        """Перевіряє доступ до складу"""
        if not self.warehouse_id:
            return
        
        user_warehouses = self.env.user.warehouse_ids
        if user_warehouses and self.warehouse_id not in user_warehouses:
            raise UserError(
                _('У вас немає доступу до складу "%s"') % self.warehouse_id.name
            )
    
    def _validate_company_consistency(self):
        """Перевіряє узгодженість компанії в документі"""
        if self.warehouse_id and self.warehouse_id.company_id != self.company_id:
            raise UserError(
                _('Склад "%s" належить іншій компанії (%s), а документ створено для компанії (%s)') % 
                (self.warehouse_id.name, self.warehouse_id.company_id.name, self.company_id.name)
            )
    
    @api.constrains('date')
    def _check_date_not_future(self):
        """Перевіряє що дата документа не в майбутньому"""
        for record in self:
            if record.date and record.date > fields.Date.today():
                raise ValidationError(
                    _('Дата документа не може бути в майбутньому: %s') % record.date
                )
    
    @api.constrains('line_ids')
    def _check_duplicate_products(self):
        """Перевіряє на дублікати товарів в позиціях"""
        for record in self:
            products = record.line_ids.mapped('nomenclature_id')
            if len(products) != len(record.line_ids):
                duplicates = []
                seen = set()
                for line in record.line_ids:
                    if line.nomenclature_id.id in seen:
                        duplicates.append(line.nomenclature_id.name)
                    seen.add(line.nomenclature_id.id)
                
                if duplicates:
                    raise ValidationError(
                        _('Знайдено дублікати товарів в документі: %s') % ', '.join(set(duplicates))
                    )
