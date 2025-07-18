from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class StockBatch(models.Model):
    _name = 'stock.batch'
    _description = 'Партія товару'
    _order = 'create_date, id'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'batch_number'

    batch_number = fields.Char(
        'Номер партії', 
        required=True, 
        readonly=True,
        index=True,
        tracking=True
    )
    
    nomenclature_id = fields.Many2one(
        'product.nomenclature', 
        'Номенклатура', 
        required=True,
        readonly=True,
        index=True,
        tracking=True
    )
    
    source_document_type = fields.Selection([
        ('receipt', 'Прихідна накладна'),
        ('inventory', 'Акт оприходування'),
        ('return', 'Повернення з сервісу'),
        ('adjustment', 'Коригування'),
        ('transfer', 'Переміщення'),
    ], 'Тип документу джерела', required=True, readonly=True, tracking=True)
    
    source_document_id = fields.Integer(
        'ID документу джерела', 
        readonly=True,
        index=True
    )
    
    source_document_number = fields.Char(
        'Номер документу джерела', 
        readonly=True,
        tracking=True
    )
    
    initial_qty = fields.Float(
        'Початкова кількість', 
        required=True, 
        readonly=True,
        digits='Product Unit of Measure',
        tracking=True
    )
    
    current_qty = fields.Float(
        'Поточна кількість', 
        compute='_compute_current_qty',
        store=True,
        digits='Product Unit of Measure',
        tracking=True
    )
    
    reserved_qty = fields.Float(
        'Зарезервована кількість', 
        default=0.0,
        digits='Product Unit of Measure',
        tracking=True
    )
    
    available_qty = fields.Float(
        'Доступна кількість',
        compute='_compute_available_qty',
        store=True,
        digits='Product Unit of Measure'
    )
    
    uom_id = fields.Many2one(
        'uom.uom', 
        'Одиниця виміру', 
        required=True,
        readonly=True,
        tracking=True
    )
    
    location_id = fields.Many2one(
        'stock.location', 
        'Локація', 
        required=True,
        readonly=True,
        tracking=True
    )
    
    company_id = fields.Many2one(
        'res.company', 
        'Компанія', 
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
        tracking=True
    )
    
    date_created = fields.Datetime(
        'Дата створення партії', 
        required=True,
        readonly=True,
        default=fields.Datetime.now,
        tracking=True
    )
    
    expiry_date = fields.Date(
        'Дата закінчення терміну', 
        help='Дата закінчення терміну придатності партії',
        tracking=True
    )
    
    is_active = fields.Boolean(
        'Активна', 
        default=True,
        help='Неактивні партії не беруться до уваги при списанні за FIFO',
        tracking=True
    )
    
    movement_ids = fields.One2many(
        'stock.batch.movement', 
        'batch_id', 
        'Рухи партії',
        readonly=True
    )
    
    serial_numbers = fields.Text(
        'Серійні номери',
        help='Серійні номери товарів у партії (для товарів з S/N обліком)'
    )
    
    notes = fields.Text('Примітки', tracking=True)
    
    state = fields.Selection([
        ('active', 'Активна'),
        ('depleted', 'Вичерпана'),
        ('expired', 'Прострочена'),
        ('blocked', 'Заблокована'),
    ], 'Статус', default='active', tracking=True, compute='_compute_state', store=True)

    _sql_constraints = [
        ('batch_nomenclature_unique', 
         'unique(batch_number, nomenclature_id)', 
         'Номер партії має бути унікальним в межах номенклатури!'),
        ('check_quantities', 
         'CHECK(current_qty >= 0 AND reserved_qty >= 0 AND initial_qty > 0)', 
         'Кількості мають бути не менше нуля, початкова кількість більше нуля!'),
    ]

    @api.depends('initial_qty', 'nomenclature_id.tracking_serial', 'serial_numbers')
    def _compute_current_qty(self):
        """Обчислює поточну кількість на основі серійних номерів або початкової кількості"""
        for batch in self:
            # Якщо товар обліковується по серійних номерах
            if batch.nomenclature_id.tracking_serial:
                # Поточна кількість = кількість серійних номерів
                batch.current_qty = len(batch._get_serial_numbers_list())
            else:
                # Для звичайних товарів - поточна кількість = початкова (поки що без списання)
                batch.current_qty = batch.initial_qty

    @api.depends('current_qty', 'reserved_qty')
    def _compute_available_qty(self):
        for batch in self:
            # Доступна кількість = поточна - зарезервована
            batch.available_qty = batch.current_qty - batch.reserved_qty

    @api.depends('current_qty', 'expiry_date', 'is_active')
    def _compute_state(self):
        today = fields.Date.today()
        for batch in self:
            if not batch.is_active:
                batch.state = 'blocked'
            elif batch.current_qty <= 0:
                batch.state = 'depleted'
            elif batch.expiry_date and batch.expiry_date < today:
                batch.state = 'expired'
            else:
                batch.state = 'active'

    @api.model
    def create_batch_from_receipt(self, nomenclature_id, receipt_number, 
                                  qty, uom_id, location_id, company_id, 
                                  date_created=None, serial_numbers=None):
        """Створює партію з прихідної накладної"""
        if date_created is None:
            date_created = fields.Datetime.now()
        
        nomenclature = self.env['product.nomenclature'].browse(nomenclature_id)
        if not nomenclature.exists():
            raise ValidationError(_('Номенклатура не знайдена!'))
        
        batch_number = receipt_number
        
        # Перевіряємо унікальність партії для номенклатури
        existing_batch = self.search([
            ('batch_number', '=', batch_number),
            ('nomenclature_id', '=', nomenclature_id)
        ])
        
        if existing_batch:
            raise ValidationError(
                _('Партія з номером %s вже існує для номенклатури %s') % 
                (batch_number, nomenclature.name)
            )
        
        batch = self.create({
            'batch_number': batch_number,
            'nomenclature_id': nomenclature_id,
            'source_document_type': 'receipt',
            'source_document_number': receipt_number,
            'initial_qty': qty,
            'uom_id': uom_id,
            'location_id': location_id,
            'company_id': company_id,
            'date_created': date_created,
            'serial_numbers': serial_numbers,
        })
        
        # Створюємо початковий рух
        self.env['stock.batch.movement'].create({
            'batch_id': batch.id,
            'movement_type': 'in',
            'operation_type': 'receipt',
            'qty': qty,
            'uom_id': uom_id,
            'location_from_id': False,
            'location_to_id': location_id,
            'document_reference': receipt_number,
            'date': date_created,
            'company_id': company_id,
            'notes': f'Створення партії з прихідної накладної {receipt_number}',
        })
        
        return batch

    def reserve_qty(self, qty):
        """Резервує кількість в партії"""
        self.ensure_one()
        if qty <= 0:
            raise ValidationError(_('Кількість для резервування має бути більше нуля!'))
        
        if self.available_qty < qty:
            raise ValidationError(
                _('Недостатньо товару в партії. Доступно: %s, потрібно: %s') % 
                (self.available_qty, qty)
            )
        
        self.reserved_qty += qty
        self.message_post(
            body=_('Зарезервовано %s %s') % (qty, self.uom_id.name),
            message_type='notification'
        )

    def unreserve_qty(self, qty):
        """Скасовує резервування кількості в партії"""
        self.ensure_one()
        if qty <= 0:
            raise ValidationError(_('Кількість для скасування резервування має бути більше нуля!'))
        
        if self.reserved_qty < qty:
            raise ValidationError(
                _('Неможливо скасувати резервування. Зарезервовано: %s, потрібно скасувати: %s') % 
                (self.reserved_qty, qty)
            )
        
        self.reserved_qty -= qty
        self.message_post(
            body=_('Скасовано резервування %s %s') % (qty, self.uom_id.name),
            message_type='notification'
        )

    def consume_qty(self, qty, operation_type='consumption', document_reference='', notes=''):
        """Списує кількість з партії (FIFO логіка застосовується на рівні вибору партій)"""
        self.ensure_one()
        if qty <= 0:
            raise ValidationError(_('Кількість для списання має бути більше нуля!'))
        
        if self.current_qty < qty:
            raise ValidationError(
                _('Недостатньо товару в партії для списання. Доступно: %s, потрібно: %s') % 
                (self.current_qty, qty)
            )
        
        # Списуємо з поточної кількості
        self.current_qty -= qty
        
        # Якщо було резервування, зменшуємо його відповідно
        if self.reserved_qty > 0:
            reserved_to_reduce = min(self.reserved_qty, qty)
            self.reserved_qty -= reserved_to_reduce
        
        # Створюємо рух
        self.env['stock.batch.movement'].create({
            'batch_id': self.id,
            'movement_type': 'out',
            'operation_type': operation_type,
            'qty': qty,
            'uom_id': self.uom_id.id,
            'location_from_id': self.location_id.id,
            'location_to_id': False,
            'document_reference': document_reference,
            'date': fields.Datetime.now(),
            'company_id': self.company_id.id,
            'notes': notes or f'Списання з партії {self.batch_number}',
        })
        
        self.message_post(
            body=_('Списано %s %s. Залишок: %s %s') % 
                 (qty, self.uom_id.name, self.current_qty, self.uom_id.name),
            message_type='notification'
        )
        
        return True

    @api.model
    def get_fifo_batches(self, nomenclature_id, location_id, qty_needed, company_id=None):
        """Повертає партії за FIFO для списання вказаної кількості"""
        if company_id is None:
            company_id = self.env.company.id
        
        domain = [
            ('nomenclature_id', '=', nomenclature_id),
            ('location_id', '=', location_id),
            ('company_id', '=', company_id),
            ('state', '=', 'active'),
            ('available_qty', '>', 0),
        ]
        
        # Сортування за FIFO (найстаріші першими)
        batches = self.search(domain, order='date_created ASC, id ASC')
        
        fifo_batches = []
        remaining_qty = qty_needed
        
        for batch in batches:
            if remaining_qty <= 0:
                break
            
            available = batch.available_qty
            if available > 0:
                take_qty = min(available, remaining_qty)
                fifo_batches.append({
                    'batch': batch,
                    'qty': take_qty,
                })
                remaining_qty -= take_qty
        
        return fifo_batches, remaining_qty

    def action_view_movements(self):
        """Відкриває рухи партії"""
        self.ensure_one()
        return {
            'name': _('Рухи партії %s') % self.batch_number,
            'type': 'ir.actions.act_window',
            'res_model': 'stock.batch.movement',
            'view_mode': 'list,form',
            'domain': [('batch_id', '=', self.id)],
            'context': {'default_batch_id': self.id},
        }

    def action_block_batch(self):
        """Блокує партію"""
        self.ensure_one()
        self.is_active = False
        self.message_post(
            body=_('Партію заблоковано'),
            message_type='notification'
        )

    def action_unblock_batch(self):
        """Розблоковує партію"""
        self.ensure_one()
        self.is_active = True
        self.message_post(
            body=_('Партію розблоковано'),
            message_type='notification'
        )

    def _get_serial_numbers_list(self):
        """Повертає список серійних номерів з партії"""
        if not self.serial_numbers:
            return []
        
        serials = []
        for line in self.serial_numbers.split('\n'):
            for serial in line.split(','):
                serial = serial.strip()
                if serial:
                    serials.append(serial)
        return serials

    @api.constrains('batch_number', 'nomenclature_id')
    def _check_unique_batch_number(self):
        """Перевірка унікальності номера партії в межах номенклатури"""
        for batch in self:
            duplicate = self.search([
                ('batch_number', '=', batch.batch_number),
                ('nomenclature_id', '=', batch.nomenclature_id.id),
                ('id', '!=', batch.id)
            ])
            if duplicate:
                raise ValidationError(_('Партія з номером %s вже існує для номенклатури %s') % 
                                   (batch.batch_number, batch.nomenclature_id.name))