from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import datetime
import logging

_logger = logging.getLogger(__name__)

class StockReceiptIncomingIntegration(models.Model):
    """Інтеграція прихідних накладних з регістром накопичення"""
    _inherit = 'stock.receipt.incoming'

    register_posted = fields.Boolean(
        'Проведено в регістрі', 
        default=False,
        readonly=True,
        help='Чи створені записи в регістрі накопичення'
    )

    def action_post_with_register(self, posting_time='current_time', custom_datetime=None):
        """Проведення документа з записами в регістр накопичення"""
        self.ensure_one()
        
        if self.state == 'posted':
            raise UserError(_('Документ уже проведено!'))
        
        if not self.line_ids:
            raise UserError(_('Додайте хоча б одну позицію до документа!'))
        
        # Встановлюємо час проведення
        if custom_datetime:
            posting_datetime = custom_datetime
        elif posting_time == 'start_of_day':
            posting_datetime = fields.Datetime.combine(self.date, datetime.time.min)
        elif posting_time == 'end_of_day':
            posting_datetime = fields.Datetime.combine(self.date, datetime.time.max)
        else:  # current_time
            posting_datetime = fields.Datetime.now()
        
        # Оновлюємо статус документа
        self.write({
            'state': 'posted',
            'posting_time': posting_time,
            'posting_datetime': posting_datetime,
        })
        
        # Створюємо записи в регістрі накопичення
        self._create_register_records(posting_datetime)
        
        self.message_post(
            body=_('Документ проведено та створено записи в регістрі накопичення'),
            message_type='notification'
        )

    def _create_register_records(self, posting_datetime):
        """Створює записи в регістрі накопичення для прихідної накладної"""
        register_model = self.env['stock.balance.register']
        
        for line in self.line_ids:
            if line.qty <= 0:
                continue
            
            # Підготовуємо локаційні виміри
            location_dims = {
                'warehouse_id': self.warehouse_id.id,
                'location_id': self.warehouse_id.lot_stock_id.id,  # Стандартна локація складу
            }
            
            # Підготовуємо дані документа для генерації партії
            receipt_doc = {
                'document_reference': self.number,
                'recorder_type': 'stock.receipt.incoming',
                'recorder_id': self.id,
                'period': posting_datetime,
            }
            
            # Обробляємо серійні номери якщо є
            serial_numbers = None
            if line.nomenclature_id.tracking_serial and line.serial_numbers_text:
                serial_numbers = [s.strip() for s in line.serial_numbers_text.replace(',', '\n').split('\n') if s.strip()]
            
            # Створюємо партію та записи в регістрі
            batch_number = register_model.create_batch_from_receipt(
                nomenclature_id=line.nomenclature_id.id,
                quantity=line.qty,
                receipt_doc=receipt_doc,
                location_dims=location_dims,
                serial_numbers=serial_numbers
            )
            
            _logger.info(f"Створено партію {batch_number} для номенклатури {line.nomenclature_id.name}")
        
        # Позначаємо що документ проведено в регістрі
        self.register_posted = True

    def action_cancel_register(self):
        """Скасування проведення в регістрі накопичення"""
        self.ensure_one()
        
        if not self.register_posted:
            raise UserError(_('Документ не був проведений в регістрі!'))
        
        # Видаляємо записи з регістра
        register_model = self.env['stock.balance.register']
        register_model.delete_records('stock.receipt.incoming', self.id)
        
        # Оновлюємо статус
        self.write({
            'state': 'draft',
            'posting_time': False,
            'posting_datetime': False,
            'register_posted': False,
        })
        
        self.message_post(
            body=_('Проведення скасовано, записи з регістра видалено'),
            message_type='notification'
        )

    def unlink(self):
        """Перевіряємо перед видаленням чи не проведений документ"""
        for record in self:
            if record.register_posted:
                raise UserError(
                    _('Неможливо видалити проведений документ %s. Спочатку скасуйте проведення.') % 
                    record.number
                )
        return super().unlink()


class StockReceiptDisposalIntegration(models.Model):
    """Інтеграція накладних списання з регістром накопичення"""
    _inherit = 'stock.receipt.disposal'

    register_posted = fields.Boolean(
        'Проведено в регістрі', 
        default=False,
        readonly=True
    )

    def action_post_with_register(self, posting_time='current_time', custom_datetime=None):
        """Проведення накладної списання з записами в регістр"""
        self.ensure_one()
        
        if self.state == 'posted':
            raise UserError(_('Документ уже проведено!'))
        
        if not self.line_ids:
            raise UserError(_('Додайте хоча б одну позицію до документа!'))
        
        # Встановлюємо час проведення
        if custom_datetime:
            posting_datetime = custom_datetime
        elif posting_time == 'start_of_day':
            posting_datetime = fields.Datetime.combine(self.date, datetime.time.min)
        elif posting_time == 'end_of_day':
            posting_datetime = fields.Datetime.combine(self.date, datetime.time.max)
        else:
            posting_datetime = fields.Datetime.now()
        
        # Перевіряємо доступність товарів за FIFO
        self._check_fifo_availability(posting_datetime)
        
        # Оновлюємо статус документа
        self.write({
            'state': 'posted',
            'posting_time': posting_time,
            'posting_datetime': posting_datetime,
        })
        
        # Створюємо записи списання в регістрі
        self._create_disposal_register_records(posting_datetime)
        
        self.message_post(
            body=_('Накладну списання проведено з FIFO логікою'),
            message_type='notification'
        )

    def _check_fifo_availability(self, posting_datetime):
        """Перевіряє доступність товарів для списання за FIFO"""
        register_model = self.env['stock.balance.register']
        
        for line in self.line_ids:
            if line.qty <= 0:
                continue
            
            # Перевіряємо загальний залишок
            dimensions = {
                'nomenclature_id': line.nomenclature_id.id,
                'warehouse_id': self.warehouse_id.id,
                'company_id': self.company_id.id,
            }
            
            balance = register_model.get_balance(period=posting_datetime, dimensions=dimensions)
            
            if balance < line.qty:
                raise ValidationError(
                    _('Недостатньо залишку для номенклатури "%s". Доступно: %s, потрібно: %s') % 
                    (line.nomenclature_id.name, balance, line.qty)
                )

    def _create_disposal_register_records(self, posting_datetime):
        """Створює записи списання в регістрі за FIFO логікою"""
        register_model = self.env['stock.balance.register']
        
        for line in self.line_ids:
            if line.qty <= 0:
                continue
            
            # Локаційні виміри
            location_dimensions = {
                'warehouse_id': self.warehouse_id.id,
            }
            
            # Отримуємо партії для списання за FIFO
            fifo_batches = register_model.fifo_consumption(
                nomenclature_id=line.nomenclature_id.id,
                quantity=line.qty,
                location_dimensions=location_dimensions,
                company_id=self.company_id.id
            )
            
            # Створюємо записи списання для кожної партії
            for batch_info in fifo_batches:
                dimensions = {
                    'nomenclature_id': line.nomenclature_id.id,
                    'warehouse_id': self.warehouse_id.id,
                    'location_id': self.warehouse_id.lot_stock_id.id,
                    'batch_number': batch_info['batch_number'],
                    'serial_number': batch_info.get('serial_number'),
                    'company_id': self.company_id.id,
                }
                
                resources = {
                    'quantity': -batch_info['quantity'],  # Від'ємна кількість для списання
                    'uom_id': line.nomenclature_id.base_uom_id.id,
                }
                
                attributes = {
                    'operation_type': 'disposal',
                    'document_reference': self.number,
                    'recorder_type': 'stock.receipt.disposal',
                    'recorder_id': self.id,
                    'period': posting_datetime,
                    'notes': f'Списання за FIFO з партії {batch_info["batch_number"]}',
                }
                
                register_model.write_record(dimensions, resources, attributes)
            
            _logger.info(f"Створено записи списання для номенклатури {line.nomenclature_id.name}")
        
        self.register_posted = True

    def action_cancel_register(self):
        """Скасування проведення списання"""
        self.ensure_one()
        
        if not self.register_posted:
            raise UserError(_('Документ не був проведений в регістрі!'))
        
        # Видаляємо записи з регістра
        register_model = self.env['stock.balance.register']
        register_model.delete_records('stock.receipt.disposal', self.id)
        
        # Оновлюємо статус
        self.write({
            'state': 'draft',
            'posting_time': False,
            'posting_datetime': False,
            'register_posted': False,
        })
        
        self.message_post(
            body=_('Списання скасовано, записи з регістра видалено'),
            message_type='notification'
        )


class StockTransferIntegration(models.Model):
    """Інтеграція переміщень з регістром накопичення"""  
    _inherit = 'stock.transfer'

    register_posted = fields.Boolean(
        'Проведено в регістрі',
        default=False, 
        readonly=True
    )

    def action_post_with_register(self):
        """Проведення переміщення з записами в регістр"""
        self.ensure_one()
        
        if self.state == 'posted':
            raise UserError(_('Переміщення уже проведено!'))
        
        # Перевіряємо доступність на складі відправника
        self._check_transfer_availability()
        
        # Проводимо переміщення
        posting_datetime = fields.Datetime.now()
        
        self.write({
            'state': 'posted',
            'posting_datetime': posting_datetime,
        })
        
        # Створюємо записи в регістрі
        self._create_transfer_register_records(posting_datetime)
        
        self.message_post(
            body=_('Переміщення проведено в регістрі накопичення'),
            message_type='notification'
        )

    def _check_transfer_availability(self):
        """Перевіряє доступність товарів на складі відправника"""
        register_model = self.env['stock.balance.register']
        
        for line in self.line_ids:
            dimensions = {
                'nomenclature_id': line.nomenclature_id.id,
                'warehouse_id': self.from_warehouse_id.id,
                'company_id': self.company_id.id,
            }
            
            balance = register_model.get_balance(dimensions=dimensions)
            
            if balance < line.qty:
                raise ValidationError(
                    _('Недостатньо залишку на складі "%s" для номенклатури "%s". Доступно: %s, потрібно: %s') % 
                    (self.from_warehouse_id.name, line.nomenclature_id.name, balance, line.qty)
                )

    def _create_transfer_register_records(self, posting_datetime):
        """Створює записи переміщення в регістрі"""
        register_model = self.env['stock.balance.register']
        
        for line in self.line_ids:
            # Списання з складу відправника за FIFO
            location_dimensions = {
                'warehouse_id': self.from_warehouse_id.id,
            }
            
            fifo_batches = register_model.fifo_consumption(
                nomenclature_id=line.nomenclature_id.id,
                quantity=line.qty,
                location_dimensions=location_dimensions,
                company_id=self.company_id.id
            )
            
            # Створюємо записи списання та надходження для кожної партії
            for batch_info in fifo_batches:
                # Запис списання
                register_model.write_record(
                    dimensions={
                        'nomenclature_id': line.nomenclature_id.id,
                        'warehouse_id': self.from_warehouse_id.id,
                        'location_id': self.from_warehouse_id.lot_stock_id.id,
                        'batch_number': batch_info['batch_number'],
                        'serial_number': batch_info.get('serial_number'),
                        'company_id': self.company_id.id,
                    },
                    resources={
                        'quantity': -batch_info['quantity'],
                        'uom_id': line.nomenclature_id.base_uom_id.id,
                    },
                    attributes={
                        'operation_type': 'transfer',
                        'document_reference': f"{self.number} (списання)",
                        'recorder_type': 'stock.transfer',
                        'recorder_id': self.id,
                        'period': posting_datetime,
                        'notes': f'Переміщення зі складу {self.from_warehouse_id.name}',
                    }
                )
                
                # Запис надходження
                register_model.write_record(
                    dimensions={
                        'nomenclature_id': line.nomenclature_id.id,
                        'warehouse_id': self.to_warehouse_id.id,
                        'location_id': self.to_warehouse_id.lot_stock_id.id,
                        'batch_number': batch_info['batch_number'],  # Партія зберігається
                        'serial_number': batch_info.get('serial_number'),
                        'company_id': self.company_id.id,
                    },
                    resources={
                        'quantity': batch_info['quantity'],
                        'uom_id': line.nomenclature_id.base_uom_id.id,
                    },
                    attributes={
                        'operation_type': 'transfer',
                        'document_reference': f"{self.number} (надходження)",
                        'recorder_type': 'stock.transfer', 
                        'recorder_id': self.id,
                        'period': posting_datetime,
                        'notes': f'Переміщення на склад {self.to_warehouse_id.name}',
                    }
                )
        
        self.register_posted = True

    def action_cancel_register(self):
        """Скасування переміщення в регістрі"""
        self.ensure_one()
        
        if not self.register_posted:
            raise UserError(_('Переміщення не було проведено в регістрі!'))
        
        # Видаляємо записи з регістра
        register_model = self.env['stock.balance.register']
        register_model.delete_records('stock.transfer', self.id)
        
        # Оновлюємо статус
        self.write({
            'state': 'draft',
            'posting_datetime': False,
            'register_posted': False,
        })
        
        self.message_post(
            body=_('Переміщення скасовано, записи з регістра видалено'),
            message_type='notification'
        )