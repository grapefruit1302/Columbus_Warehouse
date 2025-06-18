from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class ProductNomenclature(models.Model):
    _name = 'product.nomenclature'
    _description = 'Product Nomenclature'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'code'

    code = fields.Char('Код', required=True, readonly=True, default=lambda self: self._get_next_code(), tracking=True)
    name = fields.Char('Назва', required=True, translate=True, tracking=True)
    full_name = fields.Char('Повна назва', translate=True, tracking=True)
    category_ids = fields.Many2many('product.category', string='Категорії', help='Додаткові категорії продукту', tracking=True)
    species = fields.Selection(
        selection=[
            ('option1', 'Товар'),
            ('option2', 'Послуга'),
            ('option3', 'Набір'),
            ('option4', 'Генератор'),
            ('fuel', 'Паливо'),
        ],
        string='Вид',
        required=True,
        default='option1',
        help='Виберіть вид із доступних варіантів',
        tracking=True
    )
    tracking_serial = fields.Boolean('S/N', default=False, tracking=True)
    barcode_id = fields.Many2one('barcode.directory', 'Штрих-код (довідник)', index=True, help='Зв’язок із довідником штрих-кодів', tracking=True)
    barcode = fields.Char('Штрих-код', index=True, help='Штрих-код товару', tracking=True)
    description = fields.Text('Коментар', translate=True, tracking=True)
    base_uom_id = fields.Many2one(
        'uom.uom', 'Базова одиниця', required=True, tracking=True
    )
    available_uom_ids = fields.Many2many('uom.uom', string='Доступні одиниці вимірювання', tracking=True)
    uom_line_ids = fields.One2many('product.nomenclature.uom.line', 'product_id', string='Одиниці вимірювання', tracking=False)
    price_usd = fields.Float('Ціна (USD)', digits='Product Price', default=0.0, tracking=True)
    price_uah = fields.Float('Ціна (UAH)', digits='Product Price', default=0.0, tracking=True)
    category_id = fields.Many2one('product.nomenclature.category', 'Категорія', required=True, tracking=True)
    return_mechanic = fields.Boolean('Підлягає поверн. механіками', default=False, tracking=True)
    active = fields.Boolean('Active', default=True, tracking=True)
    
    fuel_type = fields.Selection(
        selection=[
            ('petrol', 'Бензин'),
            ('gas', 'Газ'),
            ('diesel', 'Дизпаливо'),
            ('oil', 'Мастило'),
        ],
        string='Вид ПММ (для палива)',
        help='Виберіть вид паливно-мастильного матеріалу',
        tracking=True
    )
    fuel_consumption_rate = fields.Float(
        'Норма витрат ПММ л/год (для генератора)',
        digits=(16, 2),
        default=0.0,
        help='Норма витрат палива для генератора в літрах на годину',
        tracking=True
    )
    oil_consumption = fields.Float(
        'Норма мастила л (для генератора)',
        digits=(16, 2),
        default=0.0,
        help='Норма витрат мастила для генератора в літрах',
        tracking=True
    )

    _sql_constraints = [
        ('code_uniq', 'unique(code)', "Код можна присвоїти тільки одному товару!"),
        ('barcode_uniq', 'unique(barcode)', "Штрих-код має бути унікальним!"),
    ]

    def write(self, vals):
        """Перевизначаємо write для форматування повідомлень про зміну uom_line_ids."""
        if 'uom_line_ids' in vals:
            for record in self:
                old_uom_lines = [(line.uom_id.name, line.coefficient, line.is_default) for line in record.uom_line_ids]
                super(ProductNomenclature, record).write(vals)
                new_uom_lines = [(line.uom_id.name, line.coefficient, line.is_default) for line in record.uom_line_ids]
                if old_uom_lines != new_uom_lines:
                    record.message_post(
                        body=f"Оновлено одиниці вимірювання: {self._format_uom_changes(old_uom_lines, new_uom_lines)}",
                        message_type='notification'
                    )
        else:
            super(ProductNomenclature, self).write(vals)
        return True



    def action_open_edit_modal(self):
        """Відкриває модальне вікно для редагування номенклатури"""
        self.ensure_one()
        
        return {
            'name': f'Редагування: {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'product.nomenclature',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('custom_stock_receipt.view_product_nomenclature_form').id,
            'target': 'new',
            'context': {
                'dialog_size': 'extra-large',
                'from_selection_modal': True,
                'default_id': self.id,
            }
        }

    def action_save_and_close_modal(self):
        """Зберігає зміни та закриває модальне вікно (опціональний метод)"""
        self.ensure_one()
        
        # Перевіряємо валідність даних
        if not self.code:
            raise UserError('Код товару є обов\'язковим!')
        if not self.name:
            raise UserError('Назва товару є обов\'язковою!')
        if not self.base_uom_id:
            raise UserError('Базова одиниця виміру є обов\'язковою!')
        
        # Стандартне збереження вже викликається автоматично
        return {'type': 'ir.actions.act_window_close'}

    def action_select_for_disposal(self):
        """Метод для вибору номенклатури в акті оприходування (оновлений)"""
        line_id = self.env.context.get('line_id')
        disposal_id = self.env.context.get('disposal_id')
        
        if line_id:
            line = self.env['stock.receipt.disposal.line'].browse(line_id)
            line.nomenclature_id = self.id
            
            # Показуємо повідомлення про вибір
            message = f'Обрано товар: {self.name}'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Товар обрано',
                    'message': message,
                    'type': 'info',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'}
                }
            }
        elif disposal_id:
            disposal = self.env['stock.receipt.disposal'].browse(disposal_id)
            new_line = self.env['stock.receipt.disposal.line'].create({
                'disposal_id': disposal_id,
                'nomenclature_id': self.id,
                'qty': 1.0,
            })
            
            message = f'Додано товар: {self.name}'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Товар додано',
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'}
                }
            }
        
        return {'type': 'ir.actions.act_window_close'}


    def _format_uom_changes(self, old_lines, new_lines):
        """Формує зрозуміле повідомлення про зміни в uom_line_ids."""
        changes = []
        old_set = set(old_lines)
        new_set = set(new_lines)

        # Додані одиниці
        for line in new_set - old_set:
            changes.append(f"Додано: {line[0]}, Коефіцієнт: {line[1]}, За замовчуванням: {'Так' if line[2] else 'Ні'}")
        # Видалені одиниці
        for line in old_set - new_set:
            changes.append(f"Видалено: {line[0]}, Коефіцієнт: {line[1]}")
        # Змінені одиниці
        for old_line, new_line in zip(old_lines, new_lines):
            if old_line != new_line and old_line[0] == new_line[0]:
                changes.append(f"Оновлено {old_line[0]}: Коефіцієнт з {old_line[1]} на {new_line[1]}, "
                               f"За замовчуванням: {'Так' if new_line[2] else 'Ні'}")

        return '; '.join(changes) if changes else "Оновлено одиниці вимірювання"

    @api.model
    def create(self, vals):
        """Перевизначення create для автоматичного додавання одиниць вимірювання."""
        uom_lines = vals.get('uom_line_ids', [])
        if not uom_lines and 'base_uom_id' in vals:
            # Якщо одиниці не вказані, додаємо базову одиницю з коефіцієнтом 1 і is_default=True
            uom_lines = [(0, 0, {
                'uom_id': vals['base_uom_id'],
                'coefficient': 1.0,
                'is_default': True,
            })]
        elif len(uom_lines) == 1:
            # Якщо додана одна одиниця, автоматично встановлюємо coefficient=1 і is_default=True
            uom_line = uom_lines[0][2]  # Отримуємо словник з команди (0, 0, {...})
            if 'coefficient' not in uom_line or uom_line['coefficient'] is None:
                uom_line['coefficient'] = 1.0
            if 'is_default' not in uom_line or uom_line['is_default'] is None:
                uom_line['is_default'] = True
            uom_lines = [(0, 0, uom_line)]
        else:
            # Якщо додано кілька одиниць, перевіряємо, що є рівно одна is_default=True
            default_count = sum(1 for line in uom_lines if line[2].get('is_default', False))
            if default_count != 1:
                raise ValidationError(_('Має бути рівно одна одиниця за замовчуванням!'))

        vals['uom_line_ids'] = uom_lines
        return super(ProductNomenclature, self).create(vals)

    def _check_and_set_default_uom(self):
        """Перевіряє та встановлює одиницю за замовчуванням для збережених записів."""
        for product in self:
            uom_lines = product.uom_line_ids
            if not uom_lines:
                raise ValidationError(_('Додайте хоча б одну одиницю вимірювання!'))
            default_uoms = uom_lines.filtered(lambda l: l.is_default)
            if len(default_uoms) > 1:
                raise ValidationError(_('Лише одна одиниця може бути за замовчуванням!'))
            elif not default_uoms and uom_lines:
                uom_lines[0].is_default = True

    @api.constrains('uom_line_ids')
    def _constrain_uom_lines(self):
        """Перевірка при зміні uom_line_ids."""
        self._check_and_set_default_uom()

    @api.onchange('species')
    def _onchange_species(self):
        """Оновлює форму при зміні виду."""
        _logger.info("Species changed to: %s", self.species)
        return {}
    
    @api.constrains('barcode')
    def _check_barcode_format(self):
        """Перевіряє, що штрих-код відповідає формату EAN13, якщо він вказаний."""
        for record in self:
            if record.barcode and not self._is_valid_ean13(record.barcode):
                raise ValidationError(_('Штрих-код EAN13 має містити 13 цифр і бути валідним!'))

    def _is_valid_ean13(self, barcode):
        """Перевіряє валідність EAN13."""
        if not barcode or not barcode.isdigit() or len(barcode) != 13:
            return False
        try:
            total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(barcode[:-1]))
            check_digit = (10 - (total % 10)) % 10
            return int(barcode[-1]) == check_digit
        except Exception as e:
            _logger.error("Помилка перевірки EAN13: %s", e)
            return False

    @api.model
    def generate_ean13(self):
        """Генерує унікальний EAN13 штрих-код."""
        sequence = self.env['ir.sequence'].next_by_code('barcode.directory.ean13')
        if not sequence:
            raise ValidationError(_('Налаштуйте послідовність для EAN13 у Налаштуваннях!'))
        prefix = '123456'
        base = sequence.zfill(6)
        barcode = prefix + base
        total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(barcode))
        check_digit = (10 - (total % 10)) % 10
        return barcode + str(check_digit)

    def action_assign_barcode(self):
        """Генерує унікальний EAN13 штрих-код і підставляє його в поле barcode."""
        barcode = self.generate_ean13()
        self.write({'barcode': barcode})
        self.env['barcode.directory'].create({
            'barcode': barcode,
            'product_id': self.id,
        })
        return True

    def action_print_label(self):
        """Відкриває модальне вікно для вибору параметрів друку етикетки."""
        if not self.barcode:
            raise ValidationError(_('Штрих-код не вказаний!'))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Друк етикетки',
            'res_model': 'product.label.wizard',
            'view_mode': 'form',
            'target': 'new',  # Відкриває у модальному вікні
            'context': {
                'default_product_id': self.id,
            },
        }
    
    @api.model
    def _get_next_code(self):
        sequence = self.env['ir.sequence'].sudo().search([('code', '=', 'product.nomenclature.sequence')], limit=1)
        if not sequence:
            sequence = self.env['ir.sequence'].sudo().create({
                'name': 'Product Nomenclature Sequence',
                'code': 'product.nomenclature.sequence',
                'prefix': 'PN',
                'padding': 5,
            })
        return sequence.next_by_id()

    @api.onchange('name')
    def _onchange_name(self):
        """Копіює name в full_name, якщо full_name порожнє."""
        for record in self:
            if not record.full_name and record.name:
                record.full_name = record.name
                _logger.info("onchange_name: name=%s, full_name=%s", record.name, record.full_name)

    @api.onchange('category_ids')
    def _onchange_category_ids(self):
        """Логує доступ до category_ids для дебагу."""
        for record in self:
            _logger.info("category_ids accessed: %s", record.category_ids.ids)

    def write(self, vals):
        """Запобігає оновленню full_name при зміні name."""
        for record in self:
            if 'name' in vals and record.full_name and 'full_name' not in vals:
                vals = vals.copy()
                vals.pop('full_name', None)
                _logger.info("write: name=%s, full_name=%s (preserved)", vals['name'], record.full_name)
            if 'category_ids' in vals:
                _logger.info("write: category_ids=%s", vals['category_ids'])
        return super(ProductNomenclature, self).write(vals)

class ProductNomenclatureUomLine(models.Model):
    _name = 'product.nomenclature.uom.line'
    _description = 'Product Nomenclature UOM Line'

    product_id = fields.Many2one('product.nomenclature', string='Продукт', required=True, ondelete='cascade')
    uom_id = fields.Many2one('uom.uom', string='Одиниця вимірювання', required=True,
                             domain=lambda self: self._get_uom_domain())
    coefficient = fields.Float('Коефіцієнт', required=True,
                              help='Коефіцієнт для конвертації відносно базової одиниці')
    is_default = fields.Boolean('За замовчуванням', default=False, required=True)

    def _get_diff(self, vals):
        """Формує зрозуміле повідомлення про зміни в одиницях вимірювання."""
        diff = []
        if 'uom_id' in vals:
            uom = self.env['uom.uom'].browse(vals['uom_id'])
            diff.append(f"Одиниця вимірювання: {uom.name}")
        if 'coefficient' in vals:
            diff.append(f"Коефіцієнт: {vals['coefficient']}")
        if 'is_default' in vals:
            diff.append(f"За замовчуванням: {'Так' if vals['is_default'] else 'Ні'}")
        return ', '.join(diff) if diff else "Оновлено одиницю вимірювання"

    @api.model
    def create(self, vals):
        """Перевизначаємо create для додавання повідомлення в журнал."""
        record = super(ProductNomenclatureUomLine, self).create(vals)
        if record.product_id:
            record.product_id.message_post(
                body=f"Додано одиницю вимірювання: {record._get_diff(vals)}",
                message_type='notification'
            )
        return record

    def write(self, vals):
        """Перевизначаємо write для додавання повідомлення в журнал."""
        for record in self:
            if record.product_id:
                old_values = {
                    'uom_id': record.uom_id.name,
                    'coefficient': record.coefficient,
                    'is_default': record.is_default,
                }
                super(ProductNomenclatureUomLine, self).write(vals)
                new_diff = record._get_diff(vals)
                record.product_id.message_post(
                    body=f"Оновлено одиницю вимірювання: {new_diff}",
                    message_type='notification'
                )
        return True

    def unlink(self):
        """Перевизначаємо unlink для додавання повідомлення в журнал."""
        for record in self:
            if record.product_id:
                record.product_id.message_post(
                    body=f"Видалено одиницю вимірювання: {record.uom_id.name}, Коефіцієнт: {record.coefficient}",
                    message_type='notification'
                )
        return super(ProductNomenclatureUomLine, self).unlink()

    @api.model
    def _get_uom_domain(self):
        category = self.env['uom.category'].search([('name', 'in', ['Одиниці', 'Unit'])], limit=1)
        if not category:
            _logger.error("Категорія 'Одиниці' або 'Unit' не знайдена в uom.category!")
            raise ValidationError(_('Категорія "Одиниці" не знайдена. Створіть її в Налаштуваннях > Одиниці вимірювання > Категорії.'))
        
        domain = [('category_id', '=', category.id)]
        if self.env.context.get('default_product_id'):
            product = self.env['product.nomenclature'].browse(self.env.context.get('default_product_id'))
            lines_to_check = product.uom_line_ids.filtered(lambda r: r != self)
            existing_uom_ids = lines_to_check.mapped('uom_id.id')
            if existing_uom_ids:
                domain.append(('id', 'not in', existing_uom_ids))
            _logger.info("Computed UOM domain: %s, Existing UOM IDs: %s", domain, existing_uom_ids)
            
            # Логування доступних одиниць
            available_uoms = self.env['uom.uom'].search(domain)
            _logger.info("Доступні одиниці вимірювання: %s", available_uoms.mapped('name'))
        
        return domain

    @api.onchange('is_default')
    def _onchange_is_default(self):
        """Скидає is_default для всіх інших одиниць і видає попередження, якщо кілька одиниць позначено."""
        for record in self:
            if record.is_default and record.product_id:
                default_lines = record.product_id.uom_line_ids.filtered(lambda l: l != record and l.is_default)
                if default_lines:
                    return {
                        'warning': {
                            'title': 'Попередження',
                            'message': 'Лише одна одиниця може бути за замовчуванням! Інші одиниці будуть скинуті.'
                        }
                    }
                for line in default_lines:
                    line.is_default = False
                    _logger.info("onchange_is_default: Set is_default=True for %s, reset others", record.uom_id.name)

    @api.onchange('uom_id')
    def _onchange_uom_id(self):
        """Автоматично встановлює coefficient=1 і is_default=True для однієї одиниці."""
        for record in self:
            if record.product_id and record.uom_id:
                lines_to_check = record.product_id.uom_line_ids.filtered(lambda r: r != record)
                existing_uom_ids = lines_to_check.mapped('uom_id.id')
                _logger.info("Existing UOM IDs: %s, Selected UOM ID: %s, Current record: %s", existing_uom_ids, record.uom_id.id, record)
                if record.uom_id.id in existing_uom_ids:
                    record.uom_id = False
                    return {
                        'warning': {
                            'title': 'Помилка',
                            'message': 'Ця одиниця вже додана для цього продукту!'
                        }
                    }
                # Якщо це єдина одиниця, встановлюємо coefficient=1 і is_default=True
                if not lines_to_check:
                    record.coefficient = 1.0
                    record.is_default = True

    def write(self, vals):
        """Скидає is_default для інших одиниць перед збереженням, якщо is_default=True."""
        if 'is_default' in vals and vals['is_default']:
            for record in self:
                if record.product_id:
                    for line in record.product_id.uom_line_ids:
                        if line != record and line.is_default:
                            line.is_default = False
                            _logger.info("write: Reset is_default for %s", line.uom_id.name)
        return super(ProductNomenclatureUomLine, self).write(vals)

    @api.constrains('is_default', 'product_id')
    def _check_one_default_uom(self):
        """Перевіряє, що лише одна одиниця позначена як за замовчуванням."""
        for record in self:
            if record.is_default:
                others = self.env['product.nomenclature.uom.line'].search([
                    ('product_id', '=', record.product_id.id),
                    ('id', '!=', record.id),
                    ('is_default', '=', True)
                ])
                if others:
                    raise ValidationError(_('Лише одна одиниця може бути за замовчуванням!'))

    @api.constrains('coefficient', 'product_id')
    def _check_coefficient(self):
        """Перевіряє, що коефіцієнт > 0, і лише одна одиниця може мати коефіцієнт = 1."""
        for record in self:
            if not record.product_id:
                continue
            if record.coefficient <= 0:
                raise ValidationError(_('Коефіцієнт має бути більшим за 0!'))
            uom_lines = record.product_id.uom_line_ids
            coefficient_one_lines = uom_lines.filtered(lambda l: abs(l.coefficient - 1.0) < 1e-6)
            if len(coefficient_one_lines) > 1:
                raise ValidationError(_('Лише одна одиниця може мати коефіцієнт, рівний 1!'))
            # Забороняємо коефіцієнт 1, якщо вже є інша одиниця з коефіцієнтом 1
            if abs(record.coefficient - 1.0) < 1e-6 and coefficient_one_lines - record:
                raise ValidationError(_('Коефіцієнт 1 вже встановлено для іншої одиниці!'))

    @api.constrains('uom_id')
    def _check_duplicate_uom(self):
        for record in self:
            if record.product_id:
                lines_to_check = record.product_id.uom_line_ids.filtered(lambda r: r != record)
                existing_uom_ids = lines_to_check.mapped('uom_id.id')
                if record.uom_id.id in existing_uom_ids:
                    raise ValidationError(_('Ця одиниця вже додана для цього продукту!'))