from odoo import models, fields, api
from odoo.exceptions import UserError

class StockTransferAddItemsWizard(models.TransientModel):
    _name = 'stock.transfer.add.items.wizard'
    _description = 'Майстер додавання товарів до переміщення'

    transfer_id = fields.Many2one(
        'stock.transfer',
        string='Документ переміщення',
        required=True,
        readonly=True
    )
    
    action_type = fields.Selection([
        ('add_all', 'Додати всі доступні товари'),
        ('replace_all', 'Замінити всі позиції на доступні товари'),
        ('add_selected', 'Додати вибрані товари'),
    ], string='Дія', default='add_all', required=True)
    
    existing_lines_count = fields.Integer(
        string='Існуючих позицій',
        compute='_compute_existing_lines_count'
    )
    
    available_items_count = fields.Integer(
        string='Доступних товарів',
        compute='_compute_available_items_count'
    )
    
    warning_message = fields.Text(
        string='Попередження',
        compute='_compute_warning_message'
    )
    
    item_ids = fields.One2many(
        'stock.transfer.add.items.wizard.line',
        'wizard_id',
        string='Товари для додавання'
    )

    @api.depends('transfer_id.line_ids')
    def _compute_existing_lines_count(self):
        for wizard in self:
            wizard.existing_lines_count = len(wizard.transfer_id.line_ids)

    @api.depends('transfer_id.available_stock_ids')
    def _compute_available_items_count(self):
        for wizard in self:
            wizard.available_items_count = len(wizard.transfer_id.available_stock_ids)

    @api.depends('action_type', 'existing_lines_count', 'available_items_count')
    def _compute_warning_message(self):
        for wizard in self:
            if wizard.action_type == 'replace_all' and wizard.existing_lines_count > 0:
                wizard.warning_message = (
                    f"⚠️ УВАГА! Всі {wizard.existing_lines_count} існуючих позицій будуть видалені "
                    f"та замінені на {wizard.available_items_count} доступних товарів!"
                )
            elif wizard.action_type == 'add_all':
                wizard.warning_message = (
                    f"ℹ️ До документа буде додано {wizard.available_items_count} нових позицій. "
                    f"Існуючі {wizard.existing_lines_count} позицій залишаться без змін."
                )
            else:
                wizard.warning_message = "Оберіть товари для додавання зі списку нижче."

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        
        transfer_id = self.env.context.get('default_transfer_id')
        if transfer_id:
            transfer = self.env['stock.transfer'].browse(transfer_id)
            
            item_lines = []
            for stock in transfer.available_stock_ids:
                existing = transfer.line_ids.filtered(
                    lambda l: l.nomenclature_id.id == stock.nomenclature_id.id and 
                             l.lot_batch == stock.lot_batch
                )
                
                item_lines.append((0, 0, {
                    'nomenclature_id': stock.nomenclature_id.id,
                    'lot_batch': stock.lot_batch,
                    'available_qty': stock.available_qty,
                    'qty_to_add': stock.available_qty if not existing else 0,
                    'selected': not existing,
                    'already_exists': bool(existing),
                    'existing_qty': existing[0].qty if existing else 0,
                }))
            
            res['item_ids'] = item_lines
        
        return res

    def action_confirm(self):
        """Підтверджує додавання товарів"""
        self.ensure_one()
        
        if self.action_type in ['add_all', 'replace_all']:
            replace_existing = (self.action_type == 'replace_all')
            return self.transfer_id._add_all_available_items(replace_existing=replace_existing)
        elif self.action_type == 'add_selected':
            return self._add_selected_items()

    def _add_selected_items(self):
        """Додає тільки вибрані товари"""
        selected_items = self.item_ids.filtered('selected')
        
        if not selected_items:
            raise UserError('Не вибрано жодного товару для додавання!')
        
        lines_to_create = []
        updated_lines = 0
        
        for item in selected_items:
            if item.qty_to_add <= 0:
                continue
                
            existing_line = self.transfer_id.line_ids.filtered(
                lambda l: l.nomenclature_id.id == item.nomenclature_id.id and 
                         l.lot_batch == item.lot_batch
            )
            
            if existing_line:
                new_qty = existing_line[0].qty + item.qty_to_add
                existing_line[0].write({'qty': new_qty})
                updated_lines += 1
            else:
                line_vals = {
                    'nomenclature_id': item.nomenclature_id.id,
                    'lot_batch': item.lot_batch,
                    'qty': item.qty_to_add,
                    'selected_uom_id': item.nomenclature_id.base_uom_id.id if item.nomenclature_id.base_uom_id else False,
                    'price_unit_no_vat': item.nomenclature_id.price_usd if hasattr(item.nomenclature_id, 'price_usd') else 0.0,
                }
                lines_to_create.append((0, 0, line_vals))
        
        if lines_to_create:
            self.transfer_id.write({'line_ids': lines_to_create})
        
        message = f"✅ Товари додані успішно!\n"
        if lines_to_create:
            message += f"➕ Створено нових позицій: {len(lines_to_create)}\n"
        if updated_lines:
            message += f"🔄 Оновлено існуючих позицій: {updated_lines}"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Операція завершена!',
                'message': message,
                'type': 'success',
            }
        }

    def action_select_all(self):
        """Вибирає всі товари"""
        self.item_ids.write({'selected': True})
        for item in self.item_ids:
            if item.qty_to_add == 0:
                item.qty_to_add = item.available_qty

    def action_deselect_all(self):
        """Знімає вибір з усіх товарів"""
        self.item_ids.write({
            'selected': False,
            'qty_to_add': 0
        })

    def action_set_max_qty_all(self):
        """Встановлює максимальну кількість для всіх вибраних товарів"""
        selected_items = self.item_ids.filtered('selected')
        for item in selected_items:
            item.qty_to_add = item.available_qty

    def action_clear_qty_all(self):
        """Очищає кількості для всіх товарів"""
        self.item_ids.write({'qty_to_add': 0})

    def action_cancel(self):
        """Скасовує операцію"""
        return {'type': 'ir.actions.act_window_close'}


class StockTransferAddItemsWizardLine(models.TransientModel):
    _name = 'stock.transfer.add.items.wizard.line'
    _description = 'Рядок майстра додавання товарів'

    wizard_id = fields.Many2one(
        'stock.transfer.add.items.wizard',
        string='Майстер',
        required=True,
        ondelete='cascade'
    )
    
    nomenclature_id = fields.Many2one(
        'product.nomenclature',
        string='Товар',
        required=True,
        readonly=True
    )
    
    lot_batch = fields.Char(
        string='Партія/Лот',
        readonly=True
    )
    
    available_qty = fields.Float(
        string='Доступна кількість',
        readonly=True
    )
    
    qty_to_add = fields.Float(
        string='Кількість до додавання',
        default=0.0
    )
    
    selected = fields.Boolean(
        string='Вибрати',
        default=True
    )
    
    already_exists = fields.Boolean(
        string='Вже існує',
        readonly=True
    )
    
    existing_qty = fields.Float(
        string='Існуюча кількість',
        readonly=True
    )

    @api.onchange('selected')
    def _onchange_selected(self):
        """При виборі товару встановлюємо кількість"""
        if self.selected and self.qty_to_add == 0:
            self.qty_to_add = self.available_qty
        elif not self.selected:
            self.qty_to_add = 0

    @api.constrains('qty_to_add')
    def _check_qty_to_add(self):
        """Перевіряємо що кількість не перевищує доступну"""
        for line in self:
            if line.qty_to_add < 0:
                raise UserError('Кількість не може бути від\'ємною!')
            if line.qty_to_add > line.available_qty:
                raise UserError(
                    f'Кількість {line.qty_to_add} перевищує доступну {line.available_qty} '
                    f'для товару "{line.nomenclature_id.name}"'
                )