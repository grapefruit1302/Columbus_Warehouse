from odoo import models, fields, api


class StockReceiptDashboard(models.TransientModel):
    _name = 'stock.receipt.dashboard'
    _description = 'Зведена сторінка приходу товарів'
    
    # Поля для відображення всіх документів у таблиці
    all_documents_ids = fields.One2many('stock.receipt.documents.line', 
                                       'dashboard_id',
                                       string='Всі документи')

    @api.model
    def default_get(self, fields):
        """Автоматично заповнюємо документи при створенні"""
        res = super().default_get(fields)
        documents = self._get_all_documents()
        res['all_documents_ids'] = documents
        return res

    def _get_all_documents(self):
        """Збираємо всі документи в одну віртуальну таблицю"""
        documents = []
        
        # Прихідні накладні
        receipts = self.env['stock.receipt.incoming'].search([], order='date desc')
        for receipt in receipts:
            documents.append((0, 0, {
                'document_type': 'receipt',
                'document_type_display': 'Прихідна накладна',
                'document_id': receipt.id,
                'number': receipt.number,
                'date': receipt.date,
                'partner_name': receipt.partner_id.name if receipt.partner_id else '-',
                # 'total_qty': receipt.total_qty,  # <-- прибрати цей рядок
                'state': receipt.state,
                'state_display': dict(receipt._fields['state'].selection)[receipt.state],
                'warehouse_name': receipt.warehouse_id.name if receipt.warehouse_id else '-',
            }))
        
        # Акти оприходування
        disposals = self.env['stock.receipt.disposal'].search([], order='date desc')
        for disposal in disposals:
            documents.append((0, 0, {
                'document_type': 'disposal',
                'document_type_display': 'Акт оприходування',
                'document_id': disposal.id,
                'number': disposal.number,
                'date': disposal.date,
                'partner_name': '-',
                # 'total_qty': disposal.total_qty,  # <-- прибрати цей рядок
                'state': disposal.state,
                'state_display': dict(disposal._fields['state'].selection)[disposal.state],
                'warehouse_name': disposal.warehouse_id.name if disposal.warehouse_id else '-',
            }))
        
        # Повернення з сервісу
        returns = self.env['stock.receipt.return'].search([], order='date desc')
        for ret in returns:
            documents.append((0, 0, {
                'document_type': 'return',
                'document_type_display': 'Повернення з сервісу',
                'document_id': ret.id,
                'number': ret.number,
                'date': ret.date,
                'partner_name': ret.service_partner_id.name if ret.service_partner_id else '-',
                # 'total_qty': ret.total_qty,  # <-- прибрати цей рядок
                'state': ret.state,
                'state_display': dict(ret._fields['state'].selection)[ret.state],
                'warehouse_name': ret.warehouse_id.name if ret.warehouse_id else '-',
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
    """Віртуальна модель для рядків таблиці документів"""
    _name = 'stock.receipt.documents.line'
    _description = 'Рядок документа приходу'
    _order = 'date desc, id desc'

    dashboard_id = fields.Many2one('stock.receipt.dashboard', 'Dashboard', ondelete='cascade')
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
    state = fields.Selection([
        ('draft', 'Чернетка'),
        ('confirmed', 'Підтверджено'),
        ('done', 'Виконано'),
        ('cancel', 'Скасовано')
    ], 'Статус')
    state_display = fields.Char('Статус (відображення)')
    warehouse_name = fields.Char('Склад')

    def action_open_document(self):
        """Відкриває оригінальний документ"""
        self.ensure_one()
        model_map = {
            'receipt': 'stock.receipt.incoming',
            'disposal': 'stock.receipt.disposal',
            'return': 'stock.receipt.return'
        }
        
        return {
            'type': 'ir.actions.act_window',
            'name': self.document_type_display,
            'res_model': model_map[self.document_type],
            'res_id': self.document_id,
            'view_mode': 'form',
            'target': 'current',
        }