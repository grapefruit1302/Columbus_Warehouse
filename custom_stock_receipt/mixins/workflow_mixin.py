from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class WorkflowMixin(models.AbstractModel):
    """Міксин для workflow операцій документів"""
    _name = 'workflow.mixin'
    _description = 'Міксин для workflow документів'

    def action_confirm(self):
        """Підтверджує документ з валідацією"""
        for record in self:
            record._validate_before_confirm()
            record._pre_confirm_actions()
            record.state = 'confirmed'
            record._post_confirm_actions()
            record.message_post(body=_('Документ підтверджено'))
            _logger.info(f"Документ {record.number} підтверджено")
    
    def action_cancel(self):
        """Скасовує документ"""
        for record in self:
            if record.state == 'posted':
                raise UserError(_('Неможливо скасувати проведений документ!'))
            
            record._pre_cancel_actions()
            record.state = 'cancelled'
            record._post_cancel_actions()
            record.message_post(body=_('Документ скасовано'))
            _logger.info(f"Документ {record.number} скасовано")
    
    def action_reset_to_draft(self):
        """Повертає документ в чернетку"""
        for record in self:
            if record.state == 'posted':
                raise UserError(_('Неможливо повернути проведений документ в чернетку!'))
            
            record._pre_reset_actions()
            record.state = 'draft'
            record.posting_datetime = False
            record._post_reset_actions()
            record.message_post(body=_('Документ повернуто в чернетку'))
            _logger.info(f"Документ {record.number} повернуто в чернетку")
    
    def action_post(self):
        """Проводить документ"""
        for record in self:
            record._validate_before_posting()
            
            if record.posting_time == 'custom_time':
                return record._show_posting_wizard()
            
            record._do_posting()
        
        return True
    
    def _do_posting(self, custom_datetime=None):
        """Виконує проведення документа"""
        for record in self:
            posting_datetime = record._calculate_posting_datetime(custom_datetime)
            
            record._pre_posting_actions(posting_datetime)
            
            record._process_document_posting(posting_datetime)
            
            record.write({
                'state': 'posted',
                'posting_datetime': posting_datetime
            })
            
            record._post_posting_actions(posting_datetime)
            record.message_post(
                body=_('Документ проведено о %s') % posting_datetime.strftime('%Y-%m-%d %H:%M:%S')
            )
            _logger.info(f"Документ {record.number} проведено о {posting_datetime}")
    
    def _calculate_posting_datetime(self, custom_datetime=None):
        """Розраховує час проведення"""
        if custom_datetime:
            return custom_datetime
        
        from datetime import datetime, time
        
        doc_date = self.date
        
        if self.posting_time == 'start_of_day':
            return datetime.combine(doc_date, time(0, 0, 0))
        elif self.posting_time == 'end_of_day':
            return datetime.combine(doc_date, time(23, 59, 59))
        else:  # current_time
            return fields.Datetime.now()
    
    def _show_posting_wizard(self):
        """Показує wizard для вибору часу проведення"""
        return {
            'name': _('Час проведення документа'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.receipt.posting.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_receipt_id': self.id,
                'default_posting_time': self.posting_time,
            }
        }
    
    
    def _pre_confirm_actions(self):
        """Дії перед підтвердженням (для перевизначення)"""
        pass
    
    def _post_confirm_actions(self):
        """Дії після підтвердження (для перевизначення)"""
        pass
    
    def _pre_cancel_actions(self):
        """Дії перед скасуванням (для перевизначення)"""
        pass
    
    def _post_cancel_actions(self):
        """Дії після скасування (для перевизначення)"""
        pass
    
    def _pre_reset_actions(self):
        """Дії перед поверненням в чернетку (для перевизначення)"""
        pass
    
    def _post_reset_actions(self):
        """Дії після повернення в чернетку (для перевизначення)"""
        pass
    
    def _pre_posting_actions(self, posting_datetime):
        """Дії перед проведенням (для перевизначення)"""
        pass
    
    def _post_posting_actions(self, posting_datetime):
        """Дії після проведення (для перевизначення)"""
        pass
    
    def _process_document_posting(self, posting_datetime):
        """Основна логіка проведення документа (має бути перевизначена)"""
        raise NotImplementedError("Subclasses must implement _process_document_posting")
    
    
    def _can_be_confirmed(self):
        """Перевіряє чи може бути документ підтверджений"""
        return self.state == 'draft'
    
    def _can_be_cancelled(self):
        """Перевіряє чи може бути документ скасований"""
        return self.state in ['draft', 'confirmed']
    
    def _can_be_posted(self):
        """Перевіряє чи може бути документ проведений"""
        return self.state == 'confirmed'
    
    def _can_be_reset(self):
        """Перевіряє чи може бути документ повернений в чернетку"""
        return self.state in ['confirmed', 'cancelled']
    
    def _get_state_color(self):
        """Повертає колір для відображення статусу"""
        colors = {
            'draft': 'secondary',
            'confirmed': 'primary', 
            'posted': 'success',
            'cancelled': 'danger'
        }
        return colors.get(self.state, 'secondary')
    
    def _get_available_actions(self):
        """Повертає список доступних дій для поточного стану"""
        actions = []
        
        if self._can_be_confirmed():
            actions.append('confirm')
        
        if self._can_be_cancelled():
            actions.append('cancel')
        
        if self._can_be_posted():
            actions.append('post')
        
        if self._can_be_reset():
            actions.append('reset')
        
        return actions
    
    @api.model
    def get_workflow_states(self):
        """Повертає список всіх можливих станів workflow"""
        return [
            ('draft', _('Чернетка')),
            ('confirmed', _('Підтверджено')),
            ('posted', _('Проведено')),
            ('cancelled', _('Скасовано'))
        ]
    
    def action_view_workflow_history(self):
        """Показує історію змін статусу документа"""
        return {
            'name': _('Історія документа %s') % self.number,
            'type': 'ir.actions.act_window',
            'res_model': 'mail.message',
            'view_mode': 'list',
            'domain': [
                ('res_id', '=', self.id),
                ('model', '=', self._name),
                ('message_type', '=', 'notification')
            ],
            'context': {'create': False, 'edit': False},
        }
