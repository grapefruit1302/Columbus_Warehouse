from odoo import models, fields, api, _

class StockBatchMovement(models.Model):
    _name = 'stock.batch.movement'
    _description = 'Рух партії'
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    batch_id = fields.Many2one(
        'stock.batch', 
        'Партія', 
        required=True,
        ondelete='cascade',
        index=True
    )
    
    movement_type = fields.Selection([
        ('in', 'Надходження'),
        ('out', 'Списання'),
        ('transfer', 'Переміщення'),
        ('transfer_in', 'Переміщення (надходження)'),
        ('transfer_out', 'Переміщення (списання)'),
        ('adjustment', 'Коригування'),
    ], 'Тип руху', required=True)
    
    operation_type = fields.Selection([
        ('receipt', 'Прихідна накладна'),
        ('inventory', 'Акт оприходування'),
        ('return', 'Повернення з сервісу'),
        ('consumption', 'Споживання'),
        ('transfer_in', 'Переміщення (надходження)'),
        ('transfer_out', 'Переміщення (списання)'),
        ('transfer', 'Переміщення'),
        ('adjustment_in', 'Коригування (+)'),
        ('adjustment_out', 'Коригування (-)'),
        ('reservation', 'Резервування'),
        ('unreservation', 'Скасування резервування'),
    ], 'Тип операції', required=True)
    
    qty = fields.Float(
        'Кількість', 
        required=True,
        digits='Product Unit of Measure'
    )
    
    uom_id = fields.Many2one(
        'uom.uom', 
        'Одиниця виміру', 
        required=True
    )
    
    location_from_id = fields.Many2one(
        'stock.location', 
        'Локація (з)'
    )
    
    location_to_id = fields.Many2one(
        'stock.location', 
        'Локація (в)'
    )
    
    document_reference = fields.Char(
        'Документ', 
        help='Посилання на документ, що спричинив рух'
    )
    
    date = fields.Datetime(
        'Дата та час', 
        required=True,
        default=fields.Datetime.now
    )
    
    company_id = fields.Many2one(
        'res.company', 
        'Компанія', 
        required=True,
        default=lambda self: self.env.company
    )
    
    user_id = fields.Many2one(
        'res.users', 
        'Користувач', 
        required=True,
        default=lambda self: self.env.user
    )
    
    notes = fields.Text('Примітки')
    
    display_name = fields.Char(
        'Назва',
        compute='_compute_display_name',
        store=True
    )

    @api.depends('movement_type', 'operation_type', 'qty', 'uom_id', 'date', 'document_reference')
    def _compute_display_name(self):
        for movement in self:
            operation_label = dict(movement._fields['operation_type'].selection).get(movement.operation_type, movement.operation_type)
            movement.display_name = f"{operation_label}: {movement.qty} {movement.uom_id.name if movement.uom_id else ''} ({movement.date.strftime('%d.%m.%Y %H:%M') if movement.date else ''})"