from odoo import models, fields, api, tools, _
from datetime import datetime, timedelta
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class StockReceiptDashboard(models.TransientModel):
    _name = 'stock.receipt.dashboard'
    _description = 'Зведена сторінка приходу товарів'
    
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
        
        return documents

    def action_create_receipt(self):
        """Створення прихідної накладної"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Прихідна накладна',
            'res_model': 'stock.receipt.incoming',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_date': fields.Date.today()},
        }
    
    def action_create_disposal(self):
        """Створення акту оприходування"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Акт оприходування',
            'res_model': 'stock.receipt.disposal',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_date': fields.Date.today()},
        }
    
    def action_create_return(self):
        """Створення повернення з сервісу"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Повернення з сервісу',
            'res_model': 'stock.receipt.return',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_date': fields.Date.today()},
        }


class StockReceiptDocumentsLine(models.Model):
    """Модель для зведеної таблиці документів приходу"""
    _name = 'stock.receipt.documents.line'
    _description = 'Зведена таблиця документів приходу'
    _order = 'date desc, id desc'
    _rec_name = 'number'
    _auto = False
    
    document_type = fields.Selection([
        ('receipt', 'Прихідна накладна'),
        ('disposal', 'Акт оприходування'),
        ('return', 'Повернення з сервісу')
    ], 'Тип документа', readonly=True)
    document_type_display = fields.Char('Тип операції', readonly=True)
    document_id = fields.Integer('ID документа', readonly=True)
    number = fields.Char('Номер', readonly=True)
    date = fields.Datetime('Дата', readonly=True)
    partner_name = fields.Char('Постачальник', readonly=True)
    company_name = fields.Char('Компанія', readonly=True)
    total_qty = fields.Float('Кількість', readonly=True)
    total_amount = fields.Float('Загальна вартість', readonly=True)
    state = fields.Selection([
        ('draft', 'Чернетка'),
        ('posted', 'Проведено'),
        ('confirmed', 'Підтверджено'),
        ('done', 'Виконано'),
        ('cancel', 'Скасовано')
    ], 'Статус', readonly=True)
    warehouse_name = fields.Char('Склад', readonly=True)
    created_by = fields.Char('Створено', readonly=True)
    posting_datetime = fields.Datetime('Час проведення', readonly=True)
    
    # Computed поля для відображення
    amount_formatted = fields.Char('Сума (форматована)', compute='_compute_amount_formatted', store=False)
    
    @api.depends('total_amount')
    def _compute_amount_formatted(self):
        """Форматує суму для відображення"""
        for record in self:
            if record.total_amount:
                record.amount_formatted = f"{record.total_amount:,.2f} грн"
            else:
                record.amount_formatted = "-"
    
    def action_open_document(self):
        """Відкриває документ для редагування"""
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
    
    def init(self):
        """Створює SQL view для зведеної таблиці"""
        # Спочатку видаляємо view якщо він існує
        self.env.cr.execute(f"DROP VIEW IF EXISTS {self._table} CASCADE")
        
        # Потім видаляємо таблицю якщо вона існує
        self.env.cr.execute(f"DROP TABLE IF EXISTS {self._table} CASCADE")
        
        sql_query = """
            CREATE OR REPLACE VIEW %s AS (
                SELECT 
                    'receipt_' || sri.id as id,
                    'receipt' as document_type,
                    'Прихідна накладна' as document_type_display,
                    sri.id as document_id,
                    sri.number,
                    sri.date,
                    rp.name as partner_name,
                    rc.name as company_name,
                    COALESCE(line_totals.total_qty, 0) as total_qty,
                    COALESCE(line_totals.total_amount, 0) as total_amount,
                    sri.state,
                    sw.name as warehouse_name,
                    up.name as created_by,
                    sri.posting_datetime
                FROM stock_receipt_incoming sri
                LEFT JOIN res_partner rp ON sri.partner_id = rp.id
                LEFT JOIN res_company rc ON sri.company_id = rc.id
                LEFT JOIN stock_warehouse sw ON sri.warehouse_id = sw.id
                LEFT JOIN res_users ru ON sri.create_uid = ru.id
                LEFT JOIN res_partner up ON ru.partner_id = up.id
                LEFT JOIN (
                    SELECT 
                        receipt_id,
                        SUM(qty) as total_qty,
                        SUM(qty * price_unit_no_vat) as total_amount
                    FROM stock_receipt_incoming_line
                    GROUP BY receipt_id
                ) line_totals ON sri.id = line_totals.receipt_id
                
                UNION ALL
                
                SELECT 
                    'disposal_' || srd.id as id,
                    'disposal' as document_type,
                    'Акт оприходування' as document_type_display,
                    srd.id as document_id,
                    srd.number,
                    srd.date,
                    '-' as partner_name,
                    rc.name as company_name,
                    COALESCE(line_totals.total_qty, 0) as total_qty,
                    COALESCE(line_totals.total_amount, 0) as total_amount,
                    srd.state,
                    sw.name as warehouse_name,
                    up2.name as created_by,
                    srd.posting_datetime
                FROM stock_receipt_disposal srd
                LEFT JOIN res_company rc ON srd.company_id = rc.id
                LEFT JOIN stock_warehouse sw ON srd.warehouse_id = sw.id
                LEFT JOIN res_users ru2 ON srd.create_uid = ru2.id
                LEFT JOIN res_partner up2 ON ru2.partner_id = up2.id
                LEFT JOIN (
                    SELECT 
                        disposal_id,
                        SUM(qty) as total_qty,
                        SUM(qty * price_unit_no_vat) as total_amount
                    FROM stock_receipt_disposal_line
                    GROUP BY disposal_id
                ) line_totals ON srd.id = line_totals.disposal_id
                
            )
        """ % self._table
        
        self.env.cr.execute(sql_query)