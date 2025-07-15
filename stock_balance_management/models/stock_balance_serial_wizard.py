from odoo import models, fields, api

class StockBalanceSerialWizard(models.TransientModel):
    _name = 'stock.balance.serial.wizard'
    _description = 'Перегляд серійних номерів у залишках'

    balance_id = fields.Many2one('stock.balance', 'Залишок', required=True)
    nomenclature_name = fields.Char('Товар', related='balance_id.nomenclature_id.name', readonly=True)
    location_info = fields.Char('Локація', compute='_compute_location_info', readonly=True)
    qty_available = fields.Float('Доступна кількість', related='balance_id.qty_available', readonly=True)
    serial_line_ids = fields.One2many('stock.balance.serial.wizard.line', 'wizard_id', 'Серійні номери')

    @api.depends('balance_id')
    def _compute_location_info(self):
        for wizard in self:
            if wizard.balance_id.location_type == 'warehouse':
                wizard.location_info = f"Склад: {wizard.balance_id.warehouse_id.name}"
            else:
                wizard.location_info = f"Працівник: {wizard.balance_id.employee_id.name}"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        balance_id = self.env.context.get('default_balance_id')
        
        if balance_id:
            balance = self.env['stock.balance'].browse(balance_id)
            res['balance_id'] = balance_id
            
            serials = balance.get_serial_numbers_list()
            res['serial_line_ids'] = [(0, 0, {'serial_number': serial}) for serial in serials]
        
        return res


class StockBalanceSerialWizardLine(models.TransientModel):
    _name = 'stock.balance.serial.wizard.line'
    _description = 'Рядок серійного номера'

    wizard_id = fields.Many2one('stock.balance.serial.wizard', 'Wizard', required=True, ondelete='cascade')
    serial_number = fields.Char('Серійний номер', required=True)