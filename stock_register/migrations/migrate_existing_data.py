"""
Міграційний скрипт для переносу даних з stock.batch та stock.balance
в новий регістр накопичення stock.balance.register
"""
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    """Основна функція міграції"""
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    _logger.info("Початок міграції даних в регістр накопичення...")
    
    # 1. Перенести дані з stock.batch
    migrate_batches(env)
    
    # 2. Перенести дані з stock.balance 
    migrate_balances(env)
    
    # 3. Створити індекси для оптимізації
    create_indexes(cr)
    
    _logger.info("Міграція завершена успішно!")

def migrate_batches(env):
    """Переносить дані партій в регістр накопичення"""
    _logger.info("Перенос партій з stock.batch...")
    
    # Перевіряємо чи існує стара таблиця
    if not table_exists(env.cr, 'stock_batch'):
        _logger.info("Таблиця stock_batch не знайдена, пропускаємо міграцію партій")
        return
    
    # Отримуємо всі партії
    env.cr.execute("""
        SELECT 
            id, batch_number, nomenclature_id, initial_qty, current_qty,
            uom_id, location_id, company_id, date_created, 
            source_document_type, source_document_number, source_document_id,
            serial_numbers
        FROM stock_batch 
        WHERE current_qty > 0
        ORDER BY date_created
    """)
    
    batches = env.cr.fetchall()
    _logger.info(f"Знайдено {len(batches)} партій для міграції")
    
    register_model = env['stock.balance.register']
    
    for batch_data in batches:
        (batch_id, batch_number, nomenclature_id, initial_qty, current_qty,
         uom_id, location_id, company_id, date_created,
         source_doc_type, source_doc_number, source_doc_id,
         serial_numbers) = batch_data
        
        try:
            # Отримуємо склад з локації
            location = env['stock.location'].browse(location_id)
            warehouse_id = location.warehouse_id.id if location.warehouse_id else None
            
            # Базові виміри
            dimensions = {
                'nomenclature_id': nomenclature_id,
                'batch_number': batch_number,
                'warehouse_id': warehouse_id,
                'location_id': location_id,
                'company_id': company_id,
            }
            
            # Ресурси
            resources = {
                'quantity': current_qty,
                'uom_id': uom_id,
            }
            
            # Реквізити
            operation_type_mapping = {
                'receipt': 'receipt',
                'inventory': 'inventory',
                'return': 'return',
                'adjustment': 'adjustment',
                'transfer': 'transfer',
            }
            
            attributes = {
                'operation_type': operation_type_mapping.get(source_doc_type, 'receipt'),
                'document_reference': source_doc_number or f'BATCH-{batch_number}',
                'recorder_type': f'migrated.{source_doc_type}',
                'recorder_id': source_doc_id or batch_id,
                'period': date_created,
                'notes': f'Мігровано з stock.batch ID: {batch_id}',
            }
            
            # Перевіряємо чи є серійні номери
            nomenclature = env['product.nomenclature'].browse(nomenclature_id)
            if nomenclature.tracking_serial and serial_numbers:
                # Для товарів з серійним обліком створюємо окремі записи
                serials = []
                for line in serial_numbers.split('\n'):
                    for serial in line.split(','):
                        serial = serial.strip()
                        if serial:
                            serials.append(serial)
                
                for serial in serials:
                    serial_dimensions = dimensions.copy()
                    serial_dimensions['serial_number'] = serial
                    
                    serial_resources = {
                        'quantity': 1.0,
                        'uom_id': uom_id,
                    }
                    
                    register_model.write_record(serial_dimensions, serial_resources, attributes)
            else:
                # Для звичайних товарів один запис
                register_model.write_record(dimensions, resources, attributes)
            
            _logger.debug(f"Мігровано партію {batch_number}")
            
        except Exception as e:
            _logger.error(f"Помилка міграції партії {batch_number}: {e}")
            continue
    
    _logger.info("Міграція партій завершена")

def migrate_balances(env):
    """Переносить дані залишків в регістр накопичення"""
    _logger.info("Перенос залишків з stock.balance...")
    
    if not table_exists(env.cr, 'stock_balance'):
        _logger.info("Таблиця stock_balance не знайдена, пропускаємо міграцію залишків")
        return
    
    # Отримуємо залишки що не покриті партіями
    env.cr.execute("""
        SELECT DISTINCT
            sb.id, sb.nomenclature_id, sb.warehouse_id, sb.location_id, 
            sb.employee_id, sb.location_type, sb.qty_on_hand,
            sb.uom_id, sb.company_id, sb.serial_numbers, sb.last_update
        FROM stock_balance sb
        LEFT JOIN stock_batch bat ON (
            bat.nomenclature_id = sb.nomenclature_id 
            AND bat.location_id = COALESCE(sb.location_id, bat.location_id)
            AND bat.company_id = sb.company_id
        )
        WHERE sb.qty_on_hand > 0 
        AND bat.id IS NULL  -- Тільки ті що не покриті партіями
        ORDER BY sb.last_update
    """)
    
    balances = env.cr.fetchall()
    _logger.info(f"Знайдено {len(balances)} залишків для міграції")
    
    register_model = env['stock.balance.register']
    
    for balance_data in balances:
        (balance_id, nomenclature_id, warehouse_id, location_id,
         employee_id, location_type, qty_on_hand, uom_id, company_id,
         serial_numbers, last_update) = balance_data
        
        try:
            # Генеруємо номер партії для мігрованих залишків
            nomenclature = env['product.nomenclature'].browse(nomenclature_id)
            batch_number = f"MIG_{nomenclature.code or 'ITEM'}_{balance_id}"
            
            # Базові виміри
            dimensions = {
                'nomenclature_id': nomenclature_id,
                'batch_number': batch_number,
                'company_id': company_id,
            }
            
            if location_type == 'warehouse' and warehouse_id:
                dimensions['warehouse_id'] = warehouse_id
                if location_id:
                    dimensions['location_id'] = location_id
            elif location_type == 'employee' and employee_id:
                dimensions['employee_id'] = employee_id
            
            # Ресурси
            resources = {
                'quantity': qty_on_hand,
                'uom_id': uom_id,
            }
            
            # Реквізити
            attributes = {
                'operation_type': 'inventory',
                'document_reference': f'MIGRATION-{balance_id}',
                'recorder_type': 'migrated.balance',
                'recorder_id': balance_id,
                'period': last_update or env.cr.now(),
                'notes': f'Мігровано з stock.balance ID: {balance_id}',
            }
            
            # Обробляємо серійні номери
            if nomenclature.tracking_serial and serial_numbers:
                serials = []
                for line in serial_numbers.split('\n'):
                    for serial in line.split(','):
                        serial = serial.strip()
                        if serial:
                            serials.append(serial)
                
                for serial in serials:
                    serial_dimensions = dimensions.copy()
                    serial_dimensions['serial_number'] = serial
                    
                    serial_resources = {
                        'quantity': 1.0,
                        'uom_id': uom_id,
                    }
                    
                    register_model.write_record(serial_dimensions, serial_resources, attributes)
            else:
                register_model.write_record(dimensions, resources, attributes)
            
            _logger.debug(f"Мігровано залишок для номенклатури {nomenclature_id}")
            
        except Exception as e:
            _logger.error(f"Помилка міграції залишку {balance_id}: {e}")
            continue
    
    _logger.info("Міграція залишків завершена")

def create_indexes(cr):
    """Створює індекси для оптимізації роботи з регістром"""
    _logger.info("Створення індексів для регістра...")
    
    indexes = [
        # Індекс для FIFO запитів
        "CREATE INDEX IF NOT EXISTS idx_stock_register_fifo "
        "ON stock_balance_register (nomenclature_id, warehouse_id, period, batch_number) "
        "WHERE active = true AND quantity > 0",
        
        # Індекс для запитів залишків
        "CREATE INDEX IF NOT EXISTS idx_stock_register_balance "
        "ON stock_balance_register (nomenclature_id, warehouse_id, location_id, batch_number, company_id) "
        "WHERE active = true",
        
        # Індекс для запитів по працівниках
        "CREATE INDEX IF NOT EXISTS idx_stock_register_employee "
        "ON stock_balance_register (nomenclature_id, employee_id, company_id) "
        "WHERE active = true",
        
        # Індекс для серійних номерів
        "CREATE INDEX IF NOT EXISTS idx_stock_register_serial "
        "ON stock_balance_register (nomenclature_id, serial_number, company_id) "
        "WHERE active = true AND serial_number IS NOT NULL",
        
        # Індекс для запитів по документам
        "CREATE INDEX IF NOT EXISTS idx_stock_register_recorder "
        "ON stock_balance_register (recorder_type, recorder_id) "
        "WHERE active = true",
        
        # Індекс для періодних запитів
        "CREATE INDEX IF NOT EXISTS idx_stock_register_period "
        "ON stock_balance_register (period, nomenclature_id, warehouse_id) "
        "WHERE active = true",
    ]
    
    for index_sql in indexes:
        try:
            cr.execute(index_sql)
            _logger.debug(f"Створено індекс: {index_sql[:50]}...")
        except Exception as e:
            _logger.warning(f"Не вдалося створити індекс: {e}")
    
    _logger.info("Індекси створено")

def table_exists(cr, table_name):
    """Перевіряє чи існує таблиця в базі даних"""
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = %s
        )
    """, [table_name])
    
    return cr.fetchone()[0]