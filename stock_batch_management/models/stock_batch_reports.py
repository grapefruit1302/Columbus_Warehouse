from odoo import models, fields, api, _

class StockBatchReportData(models.TransientModel):
    """Модель для передачі даних в QWeb звіт"""
    _name = 'stock.batch.report.data'
    _description = 'Дані звіту по партіях'

    wizard_id = fields.Many2one('stock.batch.report.wizard', 'Wizard')
    report_type = fields.Selection([
        ('movement', 'Рух товарів'),
        ('balance', 'Залишки товарів'),
    ], 'Тип звіту')
    
    # Поля для відображення
    warehouse_name = fields.Char('Склад')
    nomenclature_name = fields.Char('Номенклатура')
    batch_number = fields.Char('Номер партії')
    category_name = fields.Char('Категорія')
    
    # Дані руху
    qty_in = fields.Float('Надійшло')
    qty_out = fields.Float('Списано') 
    qty_total = fields.Float('Загальний оборот')
    movements_count = fields.Integer('Кількість рухів')
    
    # Дані залишків
    total_qty = fields.Float('Загальна кількість')
    available_qty = fields.Float('Доступна кількість')
    reserved_qty = fields.Float('Зарезервована кількість')
    batches_count = fields.Integer('Кількість партій')
    
    uom_name = fields.Char('Од. виміру')
    state = fields.Char('Статус')