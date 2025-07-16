from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, time


class StockReceiptPostingWizard(models.TransientModel):
    """Wizard для вибору часу проведення документа"""
    _name = 'stock.receipt.posting.wizard'
    _description = 'Wizard для проведення документа'

    receipt_id = fields.Many2one(
        'stock.receipt.base',  # Буде працювати з будь-яким наслідником
        'Документ',
        required=True,
        help='Документ який потрібно провести'
    )
    
    posting_time = fields.Selection([
        ('start_of_day', 'Початок дня (00:00:00)'),
        ('end_of_day', 'Кінець дня (23:59:59)'),
        ('current_time', 'Поточний час'),
        ('custom_time', 'Власний час')
    ], 'Час проведення', default='current_time', required=True)
    
    custom_datetime = fields.Datetime(
        'Власний час',
        help='Вкажіть точний час проведення документа'
    )
    
    document_date = fields.Date(
        'Дата документа',
        related='receipt_id.date',
        readonly=True
    )
    
    preview_datetime = fields.Datetime(
        'Час проведення (попередній перегляд)',
        compute='_compute_preview_datetime',
        help='Показує який час буде використаний для проведення'
    )
    
    notes = fields.Text(
        'Примітки до проведення',
        help='Додаткові примітки які будуть додані до документа'
    )
    
    @api.depends('posting_time', 'custom_datetime', 'document_date')
    def _compute_preview_datetime(self):
        """Обчислює попередній перегляд часу проведення"""
        for wizard in self:
            if not wizard.document_date:
                wizard.preview_datetime = False
                continue
            
            doc_date = wizard.document_date
            
            if wizard.posting_time == 'start_of_day':
                wizard.preview_datetime = datetime.combine(doc_date, time(0, 0, 0))
            elif wizard.posting_time == 'end_of_day':
                wizard.preview_datetime = datetime.combine(doc_date, time(23, 59, 59))
            elif wizard.posting_time == 'custom_time' and wizard.custom_datetime:
                wizard.preview_datetime = wizard.custom_datetime
            else:  # current_time
                wizard.preview_datetime = fields.Datetime.now()
    
    @api.onchange('posting_time')
    def _onchange_posting_time(self):
        """Очищає власний час при зміні типу"""
        if self.posting_time != 'custom_time':
            self.custom_datetime = False
    
    def action_post_document(self):
        """Проводить документ з вибраним часом"""
        self.ensure_one()
        
        if self.posting_time == 'custom_time' and not self.custom_datetime:
            raise UserError(_('Вкажіть власний час проведення!'))
        
        if self.custom_datetime and self.custom_datetime.date() != self.document_date:
            raise UserError(_('Дата часу проведення має відповідати даті документа!'))
        
        posting_datetime = self._get_posting_datetime()
        
        if self.notes:
            self.receipt_id.message_post(
                body=_('Примітки до проведення: %s') % self.notes
            )
        
        self.receipt_id._do_posting(posting_datetime)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Успіх'),
                'message': _('Документ %s проведено о %s') % (
                    self.receipt_id.number,
                    posting_datetime.strftime('%Y-%m-%d %H:%M:%S')
                ),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def _get_posting_datetime(self):
        """Повертає час проведення згідно з налаштуваннями"""
        doc_date = self.document_date
        
        if self.posting_time == 'start_of_day':
            return datetime.combine(doc_date, time(0, 0, 0))
        elif self.posting_time == 'end_of_day':
            return datetime.combine(doc_date, time(23, 59, 59))
        elif self.posting_time == 'custom_time':
            return self.custom_datetime
        else:  # current_time
            return fields.Datetime.now()
    
    def action_cancel(self):
        """Скасовує wizard"""
        return {'type': 'ir.actions.act_window_close'}
    
    def action_preview_posting(self):
        """Показує попередній перегляд проведення"""
        posting_datetime = self._get_posting_datetime()
        
        message = _(
            'Документ "%s" буде проведений з наступними параметрами:\n\n'
            '• Дата документа: %s\n'
            '• Час проведення: %s\n'
            '• Тип часу: %s'
        ) % (
            self.receipt_id.number,
            self.document_date.strftime('%Y-%m-%d'),
            posting_datetime.strftime('%Y-%m-%d %H:%M:%S'),
            dict(self._fields['posting_time'].selection)[self.posting_time]
        )
        
        if self.notes:
            message += _('\n• Примітки: %s') % self.notes
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Попередній перегляд проведення'),
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }
