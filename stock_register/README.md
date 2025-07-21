# Регістр накопичення залишків (1С-стиль)

## Опис
Модуль реалізує архітектуру регістра накопичення 1С для Odoo, замінюючи окремі таблиці партій та залишків єдиною структурою даних.

## Основні принципи

### Структура регістра накопичення
- **Період** - дата та час операції
- **Виміри (Измерения)** - номенклатура, склад, локація, партія, серійний номер, працівник, організація
- **Ресурси (Ресурсы)** - кількість
- **Реквізити (Реквизиты)** - тип операції, документ-джерело

### Партії як виміри
Партії більше не є окремою сутністю, а стають значеннями виміру в регістрі:
- Автоматичне створення унікальних партій при надходженні
- Формат: `НОМЕНКЛАТУРА_ДДММРР_НОМЕРДОК`
- FIFO логіка через запити до регістра

## API Методи

### Основні методи роботи з регістром

#### `get_balance(period=None, dimensions=None)`
Отримати залишок на дату (аналог 1С)

```python
# Приклад використання
register_model = self.env['stock.balance.register']

# Залишок номенклатури на складі
balance = register_model.get_balance(
    period=fields.Datetime.now(),
    dimensions={
        'nomenclature_id': 123,
        'warehouse_id': 1,
        'company_id': 1,
    }
)
```

#### `get_turnovers(period_from, period_to, dimensions=None)`
Отримати обороти за період

```python
# Обороти за місяць
turnovers = register_model.get_turnovers(
    period_from=fields.Date.today().replace(day=1),
    period_to=fields.Date.today(),
    dimensions={
        'nomenclature_id': 123,
        'warehouse_id': 1,
    }
)
# Результат: {'receipt': 100.0, 'disposal': 20.0, 'turnover': 80.0}
```

#### `write_record(dimensions, resources, attributes)`
Записати рух в регістр

```python
# Створення запису надходження
register_model.write_record(
    dimensions={
        'nomenclature_id': 123,
        'warehouse_id': 1,
        'batch_number': 'ITEM_210125_PN001',
        'company_id': 1,
    },
    resources={
        'quantity': 50.0,
        'uom_id': 1,
    },
    attributes={
        'operation_type': 'receipt',
        'document_reference': 'ПН-000001',
        'recorder_type': 'stock.receipt.incoming',
        'recorder_id': 456,
        'period': fields.Datetime.now(),
    }
)
```

#### `fifo_consumption(nomenclature_id, quantity, location_dimensions=None)`
Списання за FIFO логікою

```python
# Отримання партій для списання
fifo_batches = register_model.fifo_consumption(
    nomenclature_id=123,
    quantity=30.0,
    location_dimensions={'warehouse_id': 1},
    company_id=1
)

# Результат: список партій з кількостями для списання
for batch_info in fifo_batches:
    print(f"Партія {batch_info['batch_number']}: {batch_info['quantity']}")
```

#### `delete_records(recorder_type, recorder_id)`
Видалити записи документа при скасуванні

```python
# Скасування проведення документа
register_model.delete_records('stock.receipt.incoming', 456)
```

### Методи створення партій

#### `create_batch_from_receipt(nomenclature_id, quantity, receipt_doc, location_dims, serial_numbers=None)`
Створює партію при надходженні

```python
# Створення партії з прихідної накладної
batch_number = register_model.create_batch_from_receipt(
    nomenclature_id=123,
    quantity=100.0,
    receipt_doc={
        'document_reference': 'ПН-000001',
        'recorder_type': 'stock.receipt.incoming',
        'recorder_id': 456,
        'period': fields.Datetime.now(),
    },
    location_dims={
        'warehouse_id': 1,
        'location_id': 8,
    },
    serial_numbers=['SN001', 'SN002', 'SN003']  # Для товарів з серійним обліком
)
```

## Інтеграція з документами

### Прихідні накладні
```python
# Проведення прихідної накладної з регістром
receipt = self.env['stock.receipt.incoming'].browse(receipt_id)
receipt.action_post_with_register(posting_time='current_time')
```

### Списання
```python
# Проведення списання з FIFO логікою
disposal = self.env['stock.receipt.disposal'].browse(disposal_id)
disposal.action_post_with_register(posting_time='end_of_day')
```

### Переміщення
```python
# Проведення переміщення між складами
transfer = self.env['stock.transfer'].browse(transfer_id)
transfer.action_post_with_register()
```

## Backward Compatibility

Модуль забезпечує повну сумісність з існуючим кодом через адаптери:

### Адаптер stock.batch
```python
# Старий код продовжує працювати
batch_model = self.env['stock.batch']
fifo_batches, remaining = batch_model.get_fifo_batches(
    nomenclature_id=123,
    location_id=8, 
    qty_needed=50.0
)
```

### Адаптер stock.balance
```python
# Старі методи залишаються доступними
balance_model = self.env['stock.balance']
balance = balance_model.get_balance(
    nomenclature_id=123,
    warehouse_id=1
)

# Оновлення залишку
balance_model.update_balance(
    nomenclature_id=123,
    qty_change=10.0,
    warehouse_id=1
)
```

## Звіти

### Оборотно-сальдова відомість
```python
# Формування через wizard
wizard = self.env['stock.balance.sheet.wizard'].create({
    'date_from': fields.Date.today().replace(day=1),
    'date_to': fields.Date.today(),
    'group_by': 'nomenclature_warehouse',
})
wizard.generate_report()
```

### Рух партій
```python
# Аналіз руху конкретних партій
wizard = self.env['stock.batch.movement.wizard'].create({
    'date_from': fields.Date.today() - timedelta(days=30),
    'date_to': fields.Date.today(),
    'batch_numbers': 'ITEM_210125_PN001, ITEM_210126_PN002',
})
wizard.generate_report()
```

## SQL Оптимізація

Регістр має спеціальні індекси для швидких запитів:
- FIFO запити по партіях
- Запити залишків по номенклатурі та складу
- Фільтрація по серійних номерах
- Групування по періодах

## Приклади використання

### 1. Перевірка залишку перед списанням
```python
def check_stock_before_disposal(self, line):
    register_model = self.env['stock.balance.register']
    
    balance = register_model.get_balance(
        dimensions={
            'nomenclature_id': line.nomenclature_id.id,
            'warehouse_id': self.warehouse_id.id,
            'company_id': self.company_id.id,
        }
    )
    
    if balance < line.qty:
        raise ValidationError(
            f'Недостатньо залишку: {balance}, потрібно: {line.qty}'
        )
```

### 2. Аналіз обороту товару
```python
def analyze_product_turnover(self, nomenclature_id, warehouse_id):
    register_model = self.env['stock.balance.register']
    
    # Оборот за поточний місяць
    month_start = fields.Date.today().replace(day=1)
    turnovers = register_model.get_turnovers(
        period_from=month_start,
        period_to=fields.Date.today(),
        dimensions={
            'nomenclature_id': nomenclature_id,
            'warehouse_id': warehouse_id,
        }
    )
    
    return {
        'receipts': turnovers['receipt'],
        'disposals': turnovers['disposal'],
        'net_change': turnovers['turnover'],
    }
```

### 3. Списання по FIFO з деталізацією
```python
def dispose_with_fifo_details(self, nomenclature_id, quantity, warehouse_id):
    register_model = self.env['stock.balance.register']
    
    # Отримуємо партії для списання
    fifo_batches = register_model.fifo_consumption(
        nomenclature_id=nomenclature_id,
        quantity=quantity,
        location_dimensions={'warehouse_id': warehouse_id}
    )
    
    # Створюємо записи списання для кожної партії
    disposal_details = []
    for batch_info in fifo_batches:
        # Запис списання в регістр
        register_model.write_record(
            dimensions={
                'nomenclature_id': nomenclature_id,
                'warehouse_id': warehouse_id,
                'batch_number': batch_info['batch_number'],
                'company_id': self.env.company.id,
            },
            resources={
                'quantity': -batch_info['quantity'],  # Від'ємне для списання
                'uom_id': self.env['product.nomenclature'].browse(nomenclature_id).base_uom_id.id,
            },
            attributes={
                'operation_type': 'disposal',
                'document_reference': self.number,
                'recorder_type': self._name,
                'recorder_id': self.id,
                'notes': f'FIFO списання з партії {batch_info["batch_number"]}',
            }
        )
        
        disposal_details.append({
            'batch': batch_info['batch_number'],
            'quantity': batch_info['quantity'],
            'remaining_in_batch': batch_info['balance'] - batch_info['quantity']
        })
    
    return disposal_details
```

## Переваги нової архітектури

1. **Єдина точка істини** - всі дані про залишки в одній таблиці
2. **FIFO логіка** - автоматичне списання по найстарших партіях
3. **Масштабованість** - оптимізовані запити та індекси
4. **Сумісність** - працює з існуючим кодом
5. **Гнучкість** - підтримка серійних номерів, працівників, локацій
6. **Звітність** - оборотно-сальдові відомості та аналіз руху партій