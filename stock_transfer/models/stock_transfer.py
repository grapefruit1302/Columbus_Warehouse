from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class StockTransfer(models.Model):
    _name = 'stock.transfer'
    _description = 'Переміщення товарів'
    _order = 'date desc, number desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    number = fields.Char(
        string='Номер документа',
        required=True,
        copy=False,
        readonly=True,
        default='Новий'
    )
    
    date = fields.Date(
        string='Дата документа',
        required=True,
        default=fields.Date.context_today
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Компанія',
        required=True,
        default=lambda self: self.env.company
    )
    
    warehouse_from_id = fields.Many2one(
        'stock.warehouse',
        string='Склад відправник'
    )
    
    warehouse_to_id = fields.Many2one(
        'stock.warehouse',
        string='Склад одержувач'
    )
    
    employee_from_id = fields.Many2one(
        'hr.employee',
        string='Працівник відправник'
    )
    
    employee_to_id = fields.Many2one(
        'hr.employee',
        string='Працівник одержувач'
    )
    
    transfer_type = fields.Selection([
        ('warehouse', 'Між складами'),
        ('employee', 'Між працівниками'),
        ('warehouse_employee', 'Зі складу працівнику'),
        ('employee_warehouse', 'Від працівника на склад')
    ], string='Тип переміщення', required=True, default='warehouse')
    
    state = fields.Selection([
        ('draft', 'Чернетка'),
        ('confirmed', 'Підтверджено'),
        ('done', 'Виконано'),
        ('cancelled', 'Скасовано')
    ], string='Статус', default='draft', tracking=True)
    
    line_ids = fields.One2many(
        'stock.transfer.line',
        'transfer_id',
        string='Позиції переміщення'
    )
    
    notes = fields.Text(string='Примітки')
    
    posting_datetime = fields.Datetime(
        string='Час проведення',
        readonly=True
    )

    @api.model
    def create(self, vals):
        if vals.get('number', 'Новий') == 'Новий':
            vals['number'] = self.env['ir.sequence'].next_by_code('stock.transfer') or 'Новий'
        return super(StockTransfer, self).create(vals)

    def action_confirm(self):
        self.state = 'confirmed'
        
    def action_done(self):
        self.state = 'done'
        self.posting_datetime = fields.Datetime.now()
        
    def action_cancel(self):
        self.state = 'cancelled'
        
    def action_draft(self):
        self.state = 'draft'
        self.posting_datetime = False

    @api.onchange('transfer_type')
    def _onchange_transfer_type(self):
        # Очищаємо поля залежно від типу переміщення
        if self.transfer_type == 'warehouse':
            self.employee_from_id = False
            self.employee_to_id = False
        elif self.transfer_type == 'employee':
            self.warehouse_from_id = False
            self.warehouse_to_id = False
        elif self.transfer_type == 'warehouse_employee':
            self.employee_from_id = False
            self.warehouse_to_id = False
        elif self.transfer_type == 'employee_warehouse':
            self.warehouse_from_id = False
            self.employee_to_id = False
        
        # Очищаємо позиції при зміні типу
        self.line_ids = [(5, 0, 0)]

    def action_debug_balances(self):
        """Показує всі залишки для дебагу"""
        self.ensure_one()
        
        if 'stock.balance' not in self.env:
            raise UserError('Модуль stock.balance не встановлений!')
        
        # Отримуємо дочірні компанії
        company_ids = self._get_child_companies(self.company_id)
        _logger.info(f"ДЕБАГ: Головна компанія: {self.company_id.name} (ID: {self.company_id.id})")
        _logger.info(f"ДЕБАГ: Всі компанії для пошуку: {company_ids}")
        
        # Базовий домен - БЕЗ фільтра по qty_available для дебагу
        domain = [('company_id', 'in', company_ids)]
        
        if self.transfer_type in ['warehouse', 'warehouse_employee'] and self.warehouse_from_id:
            domain.extend([
                ('location_type', '=', 'warehouse'),
                ('warehouse_id', '=', self.warehouse_from_id.id)
            ])
            title = f'ВСІ залишки на складі {self.warehouse_from_id.name} (включно з дочірніми компаніями)'
        elif self.transfer_type in ['employee', 'employee_warehouse'] and self.employee_from_id:
            domain.extend([
                ('location_type', '=', 'employee'),
                ('employee_id', '=', self.employee_from_id.id)
            ])
            title = f'ВСІ залишки у працівника {self.employee_from_id.name} (включно з дочірніми компаніями)'
        else:
            title = 'Всі залишки головної + дочірніх компаній'
        
        _logger.info(f"ДЕБАГ: Домен для перевірки: {domain}")
        balances = self.env['stock.balance'].search(domain)
        _logger.info(f"ДЕБАГ: Знайдено {len(balances)} залишків")
        
        for balance in balances:
            _logger.info(f"ДЕБАГ: {balance.nomenclature_id.name} - qty_on_hand: {balance.qty_on_hand}, qty_available: {balance.qty_available}, компанія: {balance.company_id.name} (ID: {balance.company_id.id})")
        
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'stock.balance',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'new',
        }
    
    def _get_child_companies(self, company):
        """Повертає список ID головної компанії та всіх її дочірніх компаній"""
        company_ids = [company.id]
        
        # Рекурсивно додаємо всі дочірні компанії
        def add_children(parent_company):
            children = self.env['res.company'].search([('parent_id', '=', parent_company.id)])
            for child in children:
                if child.id not in company_ids:
                    company_ids.append(child.id)
                    add_children(child)  # Рекурсивно додаємо дочірні дочірніх
        
        add_children(company)
        return company_ids
    
    @api.depends('nomenclature_id', 'transfer_id.transfer_type', 'transfer_id.warehouse_from_id', 'transfer_id.employee_from_id')
    def _compute_available_qty_basic(self):
        """Базове обчислення доступної кількості (якщо немає модуля інтеграції)"""
        for line in self:
            if not line.nomenclature_id or not line.transfer_id:
                line.available_qty = 0.0
                continue
            
            # Якщо є модуль stock_balance_integration, то він перевизначить це поле
            if 'stock.balance' not in self.env:
                line.available_qty = 999.0  # Показуємо велику кількість якщо немає модуля залишків
                continue
                
            # Інакше встановлюємо 0 і чекаємо що модуль інтеграції перевизначить
            line.available_qty = 0.0

    def action_test_available_products(self):
        """Тестує обчислення доступних товарів"""
        self.ensure_one()
        
        # Спочатку покажемо інформацію про поточне переміщення
        _logger.info(f"=== ТЕСТ ПЕРЕМІЩЕННЯ ===")
        _logger.info(f"Transfer ID: {self.id}")
        _logger.info(f"Transfer type: {self.transfer_type}")
        _logger.info(f"Warehouse from: {self.warehouse_from_id.name if self.warehouse_from_id else 'None'} (ID: {self.warehouse_from_id.id if self.warehouse_from_id else 'None'})")
        _logger.info(f"Company: {self.company_id.name} (ID: {self.company_id.id})")
        
        # Покажемо всі склади в системі
        warehouses = self.env['stock.warehouse'].search([])
        _logger.info(f"=== ВСІ СКЛАДИ В СИСТЕМІ ===")
        for wh in warehouses:
            _logger.info(f"  - {wh.name} (ID: {wh.id}, Company: {wh.company_id.name})")
        
        # Покажемо всі залишки в компанії
        all_balances = self.env['stock.balance'].search([('company_id', '=', self.company_id.id)])
        _logger.info(f"=== ВСІ ЗАЛИШКИ В КОМПАНІЇ (ID: {self.company_id.id}) ===")
        _logger.info(f"Знайдено {len(all_balances)} залишків")
        for balance in all_balances:
            _logger.info(f"  - {balance.nomenclature_id.name}: qty_available={balance.qty_available}, qty_on_hand={balance.qty_on_hand}, "
                       f"Склад: {balance.warehouse_id.name if balance.warehouse_id else 'N/A'} (ID: {balance.warehouse_id.id if balance.warehouse_id else 'N/A'}), "
                       f"Тип: {balance.location_type}, Company: {balance.company_id.name} (ID: {balance.company_id.id})")
        
        # Також покажемо всі залишки без фільтра по компанії
        all_balances_no_filter = self.env['stock.balance'].search([])
        _logger.info(f"=== ВСІ ЗАЛИШКИ БЕЗ ФІЛЬТРА ===")
        _logger.info(f"Знайдено {len(all_balances_no_filter)} залишків")
        for balance in all_balances_no_filter[:10]:  # Тільки перші 10
            _logger.info(f"  - {balance.nomenclature_id.name}: qty_available={balance.qty_available}, "
                       f"Company: {balance.company_id.name} (ID: {balance.company_id.id}), "
                       f"Склад: {balance.warehouse_id.name if balance.warehouse_id else 'N/A'} (ID: {balance.warehouse_id.id if balance.warehouse_id else 'N/A'})")
        
        # Перевіримо конкретно наш товар
        xiaomi_balances = self.env['stock.balance'].search([('nomenclature_id.name', 'ilike', 'Роутер Xiaomi BE5000')])
        _logger.info(f"=== ЗАЛИШКИ XIAOMI BE5000 ===")
        _logger.info(f"Знайдено {len(xiaomi_balances)} залишків для Xiaomi")
        for balance in xiaomi_balances:
            _logger.info(f"  - qty_available={balance.qty_available}, qty_on_hand={balance.qty_on_hand}, "
                       f"Company: {balance.company_id.name} (ID: {balance.company_id.id}), "
                       f"Склад: {balance.warehouse_id.name if balance.warehouse_id else 'N/A'} (ID: {balance.warehouse_id.id if balance.warehouse_id else 'N/A'}), "
                       f"Тип: {balance.location_type}")
        
        # Тепер спробуємо знайти справжній товар для тесту
        first_nomenclature = self.env['product.nomenclature'].search([], limit=1)
        if not first_nomenclature:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Помилка',
                    'message': 'Немає товарів в системі!',
                    'type': 'warning',
                }
            }
        
        first_uom = self.env['uom.uom'].search([], limit=1)
        if not first_uom:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Помилка',
                    'message': 'Немає одиниць виміру в системі!',
                    'type': 'warning',
                }
            }
        
        try:
            # Створюємо тестову позицію зі справжніми ID
            test_line = self.env['stock.transfer.line'].create({
                'transfer_id': self.id,
                'nomenclature_id': first_nomenclature.id,
                'selected_uom_id': first_uom.id,
                'qty': 1.0
            })
            
            _logger.info(f"=== ТЕСТОВА ПОЗИЦІЯ СТВОРЕНА ===")
            _logger.info(f"Line ID: {test_line.id}")
            _logger.info(f"Nomenclature: {test_line.nomenclature_id.name} (ID: {test_line.nomenclature_id.id})")
            
            # Викликаємо compute
            test_line._compute_available_nomenclature_ids()
            
            _logger.info(f"=== РЕЗУЛЬТАТ COMPUTE ===")
            _logger.info(f"Available nomenclature IDs: {test_line.available_nomenclature_ids.ids}")
            
            # Видаляємо тестову позицію
            test_line.unlink()
            
        except Exception as e:
            _logger.error(f"Помилка при створенні тестової позиції: {e}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Тест завершено',
                'message': 'Перевір логи для деталей',
                'type': 'info',
            }
        }

    def action_check_balance_table(self):
        """Швидка перевірка таблиці залишків"""
        total_balances = self.env['stock.balance'].search_count([])
        warehouse_balances = self.env['stock.balance'].search_count([('location_type', '=', 'warehouse')])
        positive_balances = self.env['stock.balance'].search_count([('qty_available', '>', 0)])
        
        # Покажемо компанії де є залишки
        balances_with_companies = self.env['stock.balance'].read_group(
            [('location_type', '=', 'warehouse')],
            ['company_id'],
            ['company_id']
        )
        
        companies_info = "Компанії де є залишки:\n"
        for item in balances_with_companies:
            company_id = item['company_id'][0] if item['company_id'] else 'None'
            company_name = item['company_id'][1] if item['company_id'] else 'None'
            count = item['company_id_count']
            companies_info += f"- {company_name} (ID: {company_id}) - {count} записів\n"
        
        message = f"""
        Всього записів в stock.balance: {total_balances}
        Складських залишків: {warehouse_balances}
        З позитивним qty_available: {positive_balances}
        
        {companies_info}
        
        УВАГА: Ваше переміщення в компанії ID: {self.company_id.id} ({self.company_id.name})
        """
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Статистика залишків',
                'message': message,
                'type': 'warning',
            }
        }


class StockTransferLine(models.Model):
    _name = 'stock.transfer.line'
    _description = 'Позиція переміщення'

    transfer_id = fields.Many2one(
        'stock.transfer',
        string='Переміщення',
        required=True,
        ondelete='cascade'
    )
    
    nomenclature_id = fields.Many2one(
        'product.nomenclature',
        string='Номенклатура',
        required=True
    )
    
    # Поле для домену доступних товарів
    available_nomenclature_ids = fields.Many2many(
        'product.nomenclature',
        compute='_compute_available_nomenclature_ids',
        string='Доступні товари'
    )
    
    # Поле для показу доступної кількості
    available_qty = fields.Float(
        'Доступна кількість',
        compute='_compute_available_qty_basic',
        help='Доступна кількість в локації відправника'
    )
    
    selected_uom_id = fields.Many2one(
        'uom.uom',
        string='Одиниця виміру',
        required=True
    )
    
    qty = fields.Float(
        string='Кількість',
        required=True,
        default=1.0
    )


    @api.onchange('transfer_type')
    def _onchange_transfer_type(self):
        """Попереджуємо та очищуємо дані при зміні типу переміщення"""
        warning = None
        
        # Якщо є позиції, показуємо попередження
        if self.line_ids:
            warning = {
                'title': 'Попередження про втрату даних',
                'message': 'Зміна типу переміщення призведе до видалення всіх введених позицій товарів.'
            }
            # Очищаємо позиції
            self.line_ids = [(5, 0, 0)]
        
        # Очищаємо поля залежно від типу переміщення
        if self.transfer_type == 'warehouse':
            self.employee_from_id = False
            self.employee_to_id = False
        elif self.transfer_type == 'employee':
            self.warehouse_from_id = False
            self.warehouse_to_id = False
        elif self.transfer_type == 'warehouse_employee':
            self.employee_from_id = False
            self.warehouse_to_id = False
        elif self.transfer_type == 'employee_warehouse':
            self.warehouse_from_id = False
            self.employee_to_id = False
        
        if warning:
            return {'warning': warning}

    @api.onchange('warehouse_from_id')
    def _onchange_warehouse_from_id(self):
        """Попереджуємо та очищуємо позиції при зміні складу відправника"""
        if self.line_ids and self.warehouse_from_id:
            # Очищаємо позиції
            self.line_ids = [(5, 0, 0)]
            
            return {
                'warning': {
                    'title': 'Попередження про втрату даних',
                    'message': 'Зміна складу відправника призведе до видалення всіх введених позицій товарів, оскільки доступні товари будуть інші.'
                }
            }

    @api.onchange('employee_from_id')
    def _onchange_employee_from_id(self):
        """Попереджуємо та очищуємо позиції при зміні працівника відправника"""
        if self.line_ids and self.employee_from_id:
            # Очищаємо позиції
            self.line_ids = [(5, 0, 0)]
            
            return {
                'warning': {
                    'title': 'Попередження про втрату даних',
                    'message': 'Зміна працівника відправника призведе до видалення всіх введених позицій товарів, оскільки доступні товари будуть інші.'
                }
            }

    @api.onchange('warehouse_to_id')
    def _onchange_warehouse_to_id(self):
        """Можемо також попереджати при зміні одержувача якщо потрібно"""
        # Тут можна додати логіку якщо потрібно попереджати і при зміні одержувача
        pass

    @api.onchange('employee_to_id')
    def _onchange_employee_to_id(self):
        """Можемо також попереджати при зміні одержувача якщо потрібно"""
        # Тут можна додати логіку якщо потрібно попереджати і при зміні одержувача
        pass

    @api.depends('transfer_id.transfer_type', 'transfer_id.warehouse_from_id', 'transfer_id.employee_from_id')
    def _compute_available_nomenclature_ids(self):
        """Обчислює доступні товари залежно від відправника"""
        for line in self:
            _logger.info("=== ПОЧАТОК ОБЧИСЛЕННЯ ДОСТУПНИХ ТОВАРІВ ===")
            
            # Якщо немає переміщення
            if not line.transfer_id:
                _logger.info("Немає переміщення - показуємо всі товари")
                all_products = self.env['product.nomenclature'].search([])
                line.available_nomenclature_ids = [(6, 0, all_products.ids)]
                continue
            
            transfer = line.transfer_id
            _logger.info(f"Тип переміщення: {transfer.transfer_type}")
            _logger.info(f"Склад відправник: {transfer.warehouse_from_id.name if transfer.warehouse_from_id else 'Не вибрано'}")
            _logger.info(f"Працівник відправник: {transfer.employee_from_id.name if transfer.employee_from_id else 'Не вибрано'}")
            _logger.info(f"Головна компанія: {transfer.company_id.name} (ID: {transfer.company_id.id})")
            
            # Отримуємо всі дочірні компанії + головну
            company_ids = self._get_child_companies(transfer.company_id)
            _logger.info(f"Компанії для пошуку (головна + дочірні): {company_ids}")
            
            # Перевіряємо наявність модуля stock.balance
            if 'stock.balance' not in self.env:
                _logger.info("Модуль stock.balance відсутній - показуємо всі товари")
                all_products = self.env['product.nomenclature'].search([])
                line.available_nomenclature_ids = [(6, 0, all_products.ids)]
                continue
            
            try:
                Balance = self.env['stock.balance']
                _logger.info("Модуль stock.balance знайдено")
                
                # Формуємо домен для пошуку залишків
                domain = [
                    ('qty_available', '>', 0),
                    ('company_id', 'in', company_ids)  # Шукаємо в головній + дочірніх компаніях
                ]
                _logger.info(f"Базовий домен: {domain}")
                
                # Додаємо умови залежно від типу переміщення
                if transfer.transfer_type in ['warehouse', 'warehouse_employee'] and transfer.warehouse_from_id:
                    domain.extend([
                        ('location_type', '=', 'warehouse'),
                        ('warehouse_id', '=', transfer.warehouse_from_id.id)
                    ])
                    _logger.info(f"Фінальний домен для складу: {domain}")
                    
                elif transfer.transfer_type in ['employee', 'employee_warehouse'] and transfer.employee_from_id:
                    domain.extend([
                        ('location_type', '=', 'employee'),
                        ('employee_id', '=', transfer.employee_from_id.id)
                    ])
                    _logger.info(f"Фінальний домен для працівника: {domain}")
                    
                else:
                    _logger.info("Не вибрано відправника - показуємо всі товари")
                    all_products = self.env['product.nomenclature'].search([])
                    line.available_nomenclature_ids = [(6, 0, all_products.ids)]
                    continue
                
                # Шукаємо залишки
                balances = Balance.search(domain)
                _logger.info(f"Знайдено залишків: {len(balances)}")
                
                # Логуємо всі знайдені залишки
                for balance in balances:
                    _logger.info(f"  - {balance.nomenclature_id.name}: {balance.qty_available} шт. "
                               f"(склад: {balance.warehouse_id.name if balance.warehouse_id else 'N/A'}, "
                               f"працівник: {balance.employee_id.name if balance.employee_id else 'N/A'}, "
                               f"компанія: {balance.company_id.name} ID:{balance.company_id.id})")
                
                if balances:
                    nomenclature_ids = balances.mapped('nomenclature_id.id')
                    _logger.info(f"ID доступних товарів: {nomenclature_ids}")
                    line.available_nomenclature_ids = [(6, 0, nomenclature_ids)]
                else:
                    _logger.info("Немає доступних товарів - порожній список")
                    line.available_nomenclature_ids = [(6, 0, [])]
                    
            except Exception as e:
                _logger.error(f"Помилка при обчисленні доступних товарів: {e}")
                # При помилці показуємо всі товари
                all_products = self.env['product.nomenclature'].search([])
                line.available_nomenclature_ids = [(6, 0, all_products.ids)]
            
            _logger.info("=== КІНЕЦЬ ОБЧИСЛЕННЯ ДОСТУПНИХ ТОВАРІВ ===")
    
    def _get_child_companies(self, company):
        """Повертає список ID головної компанії та всіх її дочірніх компаній"""
        company_ids = [company.id]
        
        # Рекурсивно додаємо всі дочірні компанії
        def add_children(parent_company):
            children = self.env['res.company'].search([('parent_id', '=', parent_company.id)])
            for child in children:
                if child.id not in company_ids:
                    company_ids.append(child.id)
                    add_children(child)  # Рекурсивно додаємо дочірні дочірніх
        
        add_children(company)
        return company_ids

    @api.depends('qty', 'price_unit_no_vat', 'vat_rate')
    def _compute_amounts(self):
        for line in self:
            line.amount_no_vat = line.qty * line.price_unit_no_vat
            line.vat_amount = line.amount_no_vat * line.vat_rate / 100
            line.amount_with_vat = line.amount_no_vat + line.vat_amount

    @api.onchange('nomenclature_id')
    def _onchange_nomenclature_id(self):
        if self.nomenclature_id:
            # Встановлюємо одиницю виміру
            if hasattr(self.nomenclature_id, 'base_uom_id'):
                self.selected_uom_id = self.nomenclature_id.base_uom_id
            
            # Показуємо інформацію про доступну кількість
            if self.transfer_id and 'stock.balance' in self.env:
                Balance = self.env['stock.balance']
                transfer = self.transfer_id
                company_ids = transfer._get_child_companies(transfer.company_id)
                
                if transfer.transfer_type in ['warehouse', 'warehouse_employee'] and transfer.warehouse_from_id:
                    domain = [
                        ('nomenclature_id', '=', self.nomenclature_id.id),
                        ('location_type', '=', 'warehouse'),
                        ('warehouse_id', '=', transfer.warehouse_from_id.id),
                        ('company_id', 'in', company_ids),
                        ('qty_available', '>', 0)
                    ]
                    balances = Balance.search(domain)
                    available_qty = sum(balance.qty_available for balance in balances)
                    location_name = transfer.warehouse_from_id.name
                    
                elif transfer.transfer_type in ['employee', 'employee_warehouse'] and transfer.employee_from_id:
                    domain = [
                        ('nomenclature_id', '=', self.nomenclature_id.id),
                        ('location_type', '=', 'employee'),
                        ('employee_id', '=', transfer.employee_from_id.id),
                        ('company_id', 'in', company_ids),
                        ('qty_available', '>', 0)
                    ]
                    balances = Balance.search(domain)
                    available_qty = sum(balance.qty_available for balance in balances)
                    location_name = transfer.employee_from_id.name
                else:
                    available_qty = 0.0
                    location_name = 'Невідомо'
                
                # Показуємо повідомлення з доступною кількістю
                if available_qty > 0:
                    return {
                        'warning': {
                            'title': 'Інформація про залишки',
                            'message': f'Доступно у {location_name}: {available_qty} {self.nomenclature_id.base_uom_id.name if self.nomenclature_id.base_uom_id else "шт."}'
                        }
                    }
                else:
                    return {
                        'warning': {
                            'title': 'Увага!',
                            'message': f'Товар "{self.nomenclature_id.name}" відсутній у {location_name}!'
                        }
                    }

    @api.onchange('qty')
    def _onchange_qty(self):
        """Показує попередження при перевищенні доступної кількості"""
        # Перевіряємо тільки якщо товар вибраний і є доступна кількість
        if (self.nomenclature_id and self.qty > 0 and 
            hasattr(self, 'available_qty') and self.available_qty is not None and 
            self.available_qty < self.qty):
            return {
                'warning': {
                    'title': '⚠️ Перевищення залишків!',
                    'message': f'Ви ввели {self.qty}, але доступно тільки {self.available_qty}. '
                             f'Документ не зможе бути проведений з такою кількістю.'
                }
            }