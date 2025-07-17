from odoo import models, fields, api, _
from datetime import datetime, timedelta
from odoo.exceptions import UserError


class StockReceiptDashboard(models.TransientModel):
    _name = 'stock.receipt.dashboard'
    _description = 'Зведена сторінка приходу товарів'
    
    # Поля для відображення всіх документів у таблиці (не використовується в новій реалізації)
    # all_documents_ids = fields.One2many('stock.receipt.documents.line', 
    #                                    'dashboard_id',
    #                                    string='Всі документи')
    
    # Фільтри для пошуку
    filter_date_from = fields.Date('Дата з', default=fields.Date.today)
    filter_date_to = fields.Date('Дата по', default=fields.Date.today)
    filter_document_type = fields.Selection([
        ('all', 'Всі'),
        ('receipt', 'Прихідні накладні'),
        ('disposal', 'Акти оприходування'),
        ('return', 'Повернення з сервісу')
    ], 'Тип документа', default='all')
    filter_state = fields.Selection([
        ('all', 'Всі'),
        ('draft', 'Чернетка'),
        ('posted', 'Проведено'),
        ('confirmed', 'Підтверджено'),
        ('cancel', 'Скасовано')
    ], 'Статус', default='all')
    filter_warehouse_id = fields.Many2one('stock.warehouse', 'Склад')
    
    # Налаштування відображення колонок
    show_partner = fields.Boolean('Показати партнера', default=True)
    show_warehouse = fields.Boolean('Показати склад', default=True)
    show_total_qty = fields.Boolean('Показати кількість', default=True)
    show_total_amount = fields.Boolean('Показати вартість', default=True)
    show_created_by = fields.Boolean('Показати створювача', default=False)
    show_posting_time = fields.Boolean('Показати час проведення', default=False)
    
    # Статистичні дані
    total_documents = fields.Integer('Всього документів', compute='_compute_statistics')
    total_receipts = fields.Integer('Прихідних накладних', compute='_compute_statistics')
    total_disposals = fields.Integer('Актів оприходування', compute='_compute_statistics')
    total_returns = fields.Integer('Повернень', compute='_compute_statistics')
    total_draft = fields.Integer('Чернеток', compute='_compute_statistics')
    total_posted = fields.Integer('Проведених', compute='_compute_statistics')

    @api.model
    def default_get(self, fields):
        """Автоматично заповнюємо документи при створенні"""
        res = super().default_get(fields)
        # Документи тепер створюються динамічно в StockReceiptDocumentsLine
        return res
    
    def _compute_statistics(self):
        """Обчислюємо статистику по документам"""
        for dashboard in self:
            # Отримуємо всі документи для статистики
            documents = dashboard._get_all_documents()
            dashboard.total_documents = len(documents)
            
            # Рахуємо за типами
            dashboard.total_receipts = len([d for d in documents if d[2]['document_type'] == 'receipt'])
            dashboard.total_disposals = len([d for d in documents if d[2]['document_type'] == 'disposal'])
            dashboard.total_returns = len([d for d in documents if d[2]['document_type'] == 'return'])
            
            # Рахуємо за статусами
            dashboard.total_draft = len([d for d in documents if d[2]['state'] == 'draft'])
            dashboard.total_posted = len([d for d in documents if d[2]['state'] == 'posted'])
    
    def action_apply_filters(self):
        """Застосовує фільтри до документів"""
        self.ensure_one()
        # Фільтри тепер застосовуються динамічно в StockReceiptDocumentsLine
        # Повертаємо action для переходу до таблиці з фільтрами
        context = {
            'search_default_today': 1 if not self.filter_date_from else 0,
        }
        if self.filter_document_type and self.filter_document_type != 'all':
            context[f'search_default_{self.filter_document_type}s'] = 1
        if self.filter_state and self.filter_state != 'all':
            context[f'search_default_{self.filter_state}'] = 1
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Всі документи',
            'res_model': 'stock.receipt.documents.line',
            'view_mode': 'list',
            'target': 'current',
            'context': context,
        }
    
    def action_reset_filters(self):
        """Скидає всі фільтри"""
        self.ensure_one()
        self.write({
            'filter_date_from': fields.Date.today(),
            'filter_date_to': fields.Date.today(),
            'filter_document_type': 'all',
            'filter_state': 'all',
            'filter_warehouse_id': False,
        })
        return self.action_apply_filters()
    
    def action_export_to_excel(self):
        """Експорт документів в Excel"""
        self.ensure_one()
        # Тут можна додати логіку експорту
        raise UserError(_('Функція експорту в Excel буде додана в наступних версіях'))
    
    def action_quick_create(self):
        """Швидке створення документа"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Швидке створення',
            'res_model': 'stock.receipt.quick.create.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def _get_all_documents(self):
        """Збираємо всі документи в одну віртуальну таблицю з урахуванням фільтрів"""
        documents = []
        
        # Будуємо домен для фільтрів
        domain = []
        if self.filter_date_from and self.filter_date_to:
            domain.append(('date', '>=', self.filter_date_from))
            domain.append(('date', '<=', self.filter_date_to))
        
        if self.filter_state and self.filter_state != 'all':
            domain.append(('state', '=', self.filter_state))
        
        if self.filter_warehouse_id:
            domain.append(('warehouse_id', '=', self.filter_warehouse_id.id))
        
        # Прихідні накладні
        if self.filter_document_type in ('all', 'receipt'):
            receipts = self.env['stock.receipt.incoming'].search(domain, order='date desc')
            for receipt in receipts:
                # Обчислюємо загальну кількість
                total_qty = sum(line.qty for line in receipt.line_ids)
                total_amount = sum(line.qty * line.price_unit_no_vat for line in receipt.line_ids)
                
                documents.append((0, 0, {
                    'document_type': 'receipt',
                    'document_type_display': 'Прихідна накладна',
                    'document_id': receipt.id,
                    'number': receipt.number,
                    'date': receipt.date,
                    'partner_name': receipt.partner_id.name if receipt.partner_id else '-',
                    'total_qty': total_qty,
                    'total_amount': total_amount,
                    'state': receipt.state,
                    'state_display': dict(receipt._fields['state'].selection)[receipt.state],
                    'warehouse_name': receipt.warehouse_id.name if receipt.warehouse_id else '-',
                    'created_by': receipt.create_uid.name if receipt.create_uid else '-',
                    'posting_datetime': receipt.posting_datetime,
                    'posting_time_display': receipt._get_posting_time_label(receipt.posting_time) if receipt.posting_time else '-',
                }))
        
        # Акти оприходування
        if self.filter_document_type in ('all', 'disposal'):
            disposals = self.env['stock.receipt.disposal'].search(domain, order='date desc')
            for disposal in disposals:
                # Обчислюємо загальну кількість
                total_qty = sum(line.qty for line in disposal.line_ids)
                total_amount = sum(line.qty * line.price_unit_no_vat for line in disposal.line_ids)
                
                documents.append((0, 0, {
                    'document_type': 'disposal',
                    'document_type_display': 'Акт оприходування',
                    'document_id': disposal.id,
                    'number': disposal.number,
                    'date': disposal.date,
                    'partner_name': '-',
                    'total_qty': total_qty,
                    'total_amount': total_amount,
                    'state': disposal.state,
                    'state_display': dict(disposal._fields['state'].selection)[disposal.state],
                    'warehouse_name': disposal.warehouse_id.name if disposal.warehouse_id else '-',
                    'created_by': disposal.create_uid.name if disposal.create_uid else '-',
                    'posting_datetime': disposal.posting_datetime,
                    'posting_time_display': disposal._get_posting_time_label(disposal.posting_time) if disposal.posting_time else '-',
                }))
        
        # Повернення з сервісу
        if self.filter_document_type in ('all', 'return'):
            returns = self.env['stock.receipt.return'].search(domain, order='date desc')
            for ret in returns:
                # Обчислюємо загальну кількість
                total_qty = sum(line.qty for line in ret.line_ids)
                total_amount = sum(line.qty * line.price_unit_no_vat for line in ret.line_ids)
                
                documents.append((0, 0, {
                    'document_type': 'return',
                    'document_type_display': 'Повернення з сервісу',
                    'document_id': ret.id,
                    'number': ret.number,
                    'date': ret.date,
                    'partner_name': ret.service_partner_id.name if ret.service_partner_id else '-',
                    'total_qty': total_qty,
                    'total_amount': total_amount,
                    'state': ret.state,
                    'state_display': dict(ret._fields['state'].selection)[ret.state],
                    'warehouse_name': ret.warehouse_id.name if ret.warehouse_id else '-',
                    'created_by': ret.create_uid.name if ret.create_uid else '-',
                    'posting_datetime': ret.posting_datetime,
                    'posting_time_display': ret._get_posting_time_label(ret.posting_time) if ret.posting_time else '-',
                }))
        
        # Сортуємо по даті (найновіші першими)
        documents.sort(key=lambda x: x[2]['date'], reverse=True)
        
        return documents

    def action_create_receipt(self):
        """Створення нової прихідної накладної"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Нова прихідна накладна',
            'res_model': 'stock.receipt.incoming',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_state': 'draft'},
        }

    def action_create_disposal(self):
        """Створення нового акта оприходування"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Новий акт оприходування',
            'res_model': 'stock.receipt.disposal',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_state': 'draft'},
        }

    def action_create_return(self):
        """Створення нового повернення з сервісу"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Нове повернення з сервісу',
            'res_model': 'stock.receipt.return',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_state': 'draft'},
        }


class StockReceiptDocumentsLine(models.TransientModel):
    """Модель для рядків таблиці документів"""
    _name = 'stock.receipt.documents.line'
    _description = 'Рядок документа приходу'
    _order = 'date desc, id desc'

    document_type = fields.Selection([
        ('receipt', 'Прихідна накладна'),
        ('disposal', 'Акт оприходування'),
        ('return', 'Повернення з сервісу')
    ], 'Тип документа')
    document_type_display = fields.Char('Тип операції')
    document_id = fields.Integer('ID документа')
    number = fields.Char('Номер')
    date = fields.Datetime('Дата')
    partner_name = fields.Char('Партнер/Сервіс')
    total_qty = fields.Float('Кількість')
    total_amount = fields.Float('Загальна вартість')
    state = fields.Selection([
        ('draft', 'Чернетка'),
        ('posted', 'Проведено'),
        ('confirmed', 'Підтверджено'),
        ('done', 'Виконано'),
        ('cancel', 'Скасовано')
    ], 'Статус')
    state_display = fields.Char('Статус (відображення)')
    warehouse_name = fields.Char('Склад')
    created_by = fields.Char('Створено')
    posting_datetime = fields.Datetime('Час проведення')
    posting_time_display = fields.Char('Час проведення (відображення)')
    
    # Поля для кольорового кодування
    priority = fields.Selection([
        ('low', 'Низький'),
        ('normal', 'Нормальний'),
        ('high', 'Високий'),
        ('urgent', 'Терміново')
    ], 'Пріоритет', default='normal')
    
    # Computed поля для відображення
    state_color = fields.Char('Колір статусу', compute='_compute_state_color')
    amount_formatted = fields.Char('Сума (форматована)', compute='_compute_amount_formatted')
    
    @api.depends('state')
    def _compute_state_color(self):
        """Обчислюємо колір для статусу"""
        color_map = {
            'draft': 'muted',
            'posted': 'info',
            'confirmed': 'success',
            'done': 'success',
            'cancel': 'danger'
        }
        for line in self:
            line.state_color = color_map.get(line.state, 'muted')
    
    @api.depends('total_amount')
    def _compute_amount_formatted(self):
        """Форматуємо суму для відображення"""
        for line in self:
            if line.total_amount:
                line.amount_formatted = f"{line.total_amount:,.2f} грн"
            else:
                line.amount_formatted = "-"

    def action_open_document(self):
        """Відкриває оригінальний документ"""
        self.ensure_one()
        if not self.document_id:
            return {'type': 'ir.actions.act_window_close'}
            
        model_map = {
            'receipt': 'stock.receipt.incoming',
            'disposal': 'stock.receipt.disposal',
            'return': 'stock.receipt.return'
        }
        
        if self.document_type not in model_map:
            return {'type': 'ir.actions.act_window_close'}
        
        return {
            'type': 'ir.actions.act_window',
            'name': self.document_type_display,
            'res_model': model_map[self.document_type],
            'res_id': self.document_id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_duplicate_document(self):
        """Створює копію документа"""
        self.ensure_one()
        if not self.document_id:
            return {'type': 'ir.actions.act_window_close'}
            
        model_map = {
            'receipt': 'stock.receipt.incoming',
            'disposal': 'stock.receipt.disposal',
            'return': 'stock.receipt.return'
        }
        
        if self.document_type not in model_map:
            return {'type': 'ir.actions.act_window_close'}
        
        model = model_map[self.document_type]
        original_doc = self.env[model].browse(self.document_id)
        
        if not original_doc.exists():
            return {'type': 'ir.actions.act_window_close'}
        
        # Створюємо копію
        new_doc = original_doc.copy()
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Копія {self.document_type_display}',
            'res_model': model,
            'res_id': new_doc.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_print_document(self):
        """Друк документа"""
        self.ensure_one()
        model_map = {
            'receipt': 'stock.receipt.incoming',
            'disposal': 'stock.receipt.disposal',
            'return': 'stock.receipt.return'
        }
        
        model = model_map[self.document_type]
        document = self.env[model].browse(self.document_id)
        
        return document.action_print_document()
    
    def action_post_document(self):
        """Проведення документа"""
        self.ensure_one()
        model_map = {
            'receipt': 'stock.receipt.incoming',
            'disposal': 'stock.receipt.disposal',
            'return': 'stock.receipt.return'
        }
        
        model = model_map[self.document_type]
        document = self.env[model].browse(self.document_id)
        
        if document.state == 'draft':
            return document.action_post()
        else:
            raise UserError(_('Документ можна проводити тільки зі статусом "Чернетка"'))
    
    def action_cancel_document(self):
        """Скасування документа"""
        self.ensure_one()
        model_map = {
            'receipt': 'stock.receipt.incoming',
            'disposal': 'stock.receipt.disposal',
            'return': 'stock.receipt.return'
        }
        
        model = model_map[self.document_type]
        document = self.env[model].browse(self.document_id)
        
        return document.action_cancel()
    
    @api.model
    def create_all_documents(self):
        """Створюємо всі документи в транзієнтній моделі"""
        # Спочатку видаляємо всі існуючі записи
        self.search([]).unlink()
        
        # Прихідні накладні
        receipts = self.env['stock.receipt.incoming'].search([], order='date desc')
        for receipt in receipts:
            total_qty = sum(line.qty for line in receipt.line_ids)
            total_amount = sum(line.qty * line.price_unit_no_vat for line in receipt.line_ids)
            
            self.create({
                'document_type': 'receipt',
                'document_type_display': 'Прихідна накладна',
                'document_id': receipt.id,
                'number': receipt.number,
                'date': receipt.date,
                'partner_name': receipt.partner_id.name if receipt.partner_id else '-',
                'total_qty': total_qty,
                'total_amount': total_amount,
                'state': receipt.state,
                'state_display': dict(receipt._fields['state'].selection)[receipt.state],
                'warehouse_name': receipt.warehouse_id.name if receipt.warehouse_id else '-',
                'created_by': receipt.create_uid.name if receipt.create_uid else '-',
                'posting_datetime': receipt.posting_datetime,
                'posting_time_display': receipt._get_posting_time_label(receipt.posting_time) if receipt.posting_time else '-',
                'amount_formatted': f"{total_amount:,.2f} грн" if total_amount else "-",
                'state_color': self._get_state_color(receipt.state),
                'priority': 'normal',
            })
        
        # Акти оприходування
        disposals = self.env['stock.receipt.disposal'].search([], order='date desc')
        for disposal in disposals:
            total_qty = sum(line.qty for line in disposal.line_ids)
            total_amount = sum(line.qty * line.price_unit_no_vat for line in disposal.line_ids)
            
            self.create({
                'document_type': 'disposal',
                'document_type_display': 'Акт оприходування',
                'document_id': disposal.id,
                'number': disposal.number,
                'date': disposal.date,
                'partner_name': '-',
                'total_qty': total_qty,
                'total_amount': total_amount,
                'state': disposal.state,
                'state_display': dict(disposal._fields['state'].selection)[disposal.state],
                'warehouse_name': disposal.warehouse_id.name if disposal.warehouse_id else '-',
                'created_by': disposal.create_uid.name if disposal.create_uid else '-',
                'posting_datetime': disposal.posting_datetime,
                'posting_time_display': disposal._get_posting_time_label(disposal.posting_time) if disposal.posting_time else '-',
                'amount_formatted': f"{total_amount:,.2f} грн" if total_amount else "-",
                'state_color': self._get_state_color(disposal.state),
                'priority': 'normal',
            })
        
        # Повернення з сервісу
        returns = self.env['stock.receipt.return'].search([], order='date desc')
        for ret in returns:
            total_qty = sum(line.qty for line in ret.line_ids)
            total_amount = sum(line.qty * line.price_unit_no_vat for line in ret.line_ids)
            
            self.create({
                'document_type': 'return',
                'document_type_display': 'Повернення з сервісу',
                'document_id': ret.id,
                'number': ret.number,
                'date': ret.date,
                'partner_name': ret.service_partner_id.name if ret.service_partner_id else '-',
                'total_qty': total_qty,
                'total_amount': total_amount,
                'state': ret.state,
                'state_display': dict(ret._fields['state'].selection)[ret.state],
                'warehouse_name': ret.warehouse_id.name if ret.warehouse_id else '-',
                'created_by': ret.create_uid.name if ret.create_uid else '-',
                'posting_datetime': ret.posting_datetime,
                'posting_time_display': ret._get_posting_time_label(ret.posting_time) if ret.posting_time else '-',
                'amount_formatted': f"{total_amount:,.2f} грн" if total_amount else "-",
                'state_color': self._get_state_color(ret.state),
                'priority': 'normal',
            })
        
        return True
    
    def _get_state_color(self, state):
        """Повертає колір для статусу"""
        color_map = {
            'draft': 'muted',
            'posted': 'info',
            'confirmed': 'success',
            'done': 'success',
            'cancel': 'danger'
        }
        return color_map.get(state, 'muted')
    
    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """Переопределяем search_read для автоматичного створення документів"""
        # Якщо в контексті є create_documents, створюємо документи
        if self.env.context.get('create_documents'):
            self.create_all_documents()
        
        return super().search_read(domain, fields, offset, limit, order)