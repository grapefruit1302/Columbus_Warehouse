#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    """
    Міграція серійних номерів з текстових полів до централізованої таблиці stock.serial.number
    """
    _logger.info("Початок міграції серійних номерів до централізованої таблиці...")
    
    with api.Environment.manage():
        env = api.Environment(cr, SUPERUSER_ID, {})
        
        if 'stock.serial.number' not in env:
            _logger.warning("Модель stock.serial.number не знайдена, пропускаємо міграцію")
            return
        
        migrated_count = 0
        
        try:
            _logger.info("Міграція серійних номерів з stock.batch...")
            batches = env['stock.batch'].search([('serial_numbers', '!=', False)])
            for batch in batches:
                if batch.serial_numbers:
                    serials = _parse_serial_numbers(batch.serial_numbers)
                    for serial in serials:
                        if serial:
                            env['stock.serial.number'].create({
                                'serial_number': serial,
                                'nomenclature_id': batch.nomenclature_id.id if batch.nomenclature_id else False,
                                'document_type': 'batch',
                                'document_id': batch.id,
                                'current_location_type': 'warehouse',
                                'warehouse_id': False,  # Буде оновлено пізніше з balance
                                'employee_id': False,
                                'batch_id': batch.id,
                                'date_created': batch.date_created or batch.create_date,
                                'source_document_type': batch.source_document_type,
                                'source_document_number': batch.source_document_number,
                            })
                            migrated_count += 1
            
            _logger.info("Міграція серійних номерів з stock.balance...")
            balances = env['stock.balance'].search([('serial_numbers', '!=', False)])
            for balance in balances:
                if balance.serial_numbers:
                    serials = _parse_serial_numbers(balance.serial_numbers)
                    for serial in serials:
                        if serial:
                            existing = env['stock.serial.number'].search([
                                ('serial_number', '=', serial),
                                ('nomenclature_id', '=', balance.nomenclature_id.id)
                            ], limit=1)
                            
                            if existing:
                                existing.write({
                                    'current_location_type': balance.location_type,
                                    'warehouse_id': balance.warehouse_id.id if balance.warehouse_id else False,
                                    'employee_id': balance.employee_id.id if balance.employee_id else False,
                                })
                            else:
                                # Створюємо новий запис
                                env['stock.serial.number'].create({
                                    'serial_number': serial,
                                    'nomenclature_id': balance.nomenclature_id.id,
                                    'document_type': 'balance',
                                    'document_id': balance.id,
                                    'current_location_type': balance.location_type,
                                    'warehouse_id': balance.warehouse_id.id if balance.warehouse_id else False,
                                    'employee_id': balance.employee_id.id if balance.employee_id else False,
                                    'batch_id': balance.batch_id.id if balance.batch_id else False,
                                    'date_created': balance.batch_id.date_created if balance.batch_id else balance.create_date,
                                })
                                migrated_count += 1
            
            _logger.info("Міграція серійних номерів з stock.receipt.incoming...")
            receipts = env['stock.receipt.incoming'].search([])
            for receipt in receipts:
                for line in receipt.line_ids:
                    if line.serial_numbers:
                        serials = _parse_serial_numbers(line.serial_numbers)
                        for serial in serials:
                            if serial:
                                existing = env['stock.serial.number'].search([
                                    ('serial_number', '=', serial),
                                    ('nomenclature_id', '=', line.nomenclature_id.id)
                                ], limit=1)
                                
                                if not existing:
                                    env['stock.serial.number'].create({
                                        'serial_number': serial,
                                        'nomenclature_id': line.nomenclature_id.id,
                                        'document_type': 'incoming',
                                        'document_id': receipt.id,
                                        'current_location_type': 'warehouse',
                                        'warehouse_id': receipt.warehouse_id.id if receipt.warehouse_id else False,
                                        'employee_id': False,
                                        'date_created': receipt.date,
                                        'source_document_type': 'receipt',
                                        'source_document_number': receipt.number,
                                    })
                                    migrated_count += 1
            
            _logger.info("Міграція серійних номерів з stock.receipt.disposal...")
            disposals = env['stock.receipt.disposal'].search([])
            for disposal in disposals:
                for line in disposal.line_ids:
                    if line.serial_numbers:
                        serials = _parse_serial_numbers(line.serial_numbers)
                        for serial in serials:
                            if serial:
                                existing = env['stock.serial.number'].search([
                                    ('serial_number', '=', serial),
                                    ('nomenclature_id', '=', line.nomenclature_id.id)
                                ], limit=1)
                                
                                if not existing:
                                    env['stock.serial.number'].create({
                                        'serial_number': serial,
                                        'nomenclature_id': line.nomenclature_id.id,
                                        'document_type': 'disposal',
                                        'document_id': disposal.id,
                                        'current_location_type': 'warehouse',
                                        'warehouse_id': disposal.warehouse_id.id if disposal.warehouse_id else False,
                                        'employee_id': False,
                                        'date_created': disposal.date,
                                        'source_document_type': 'inventory',
                                        'source_document_number': disposal.number,
                                    })
                                    migrated_count += 1
            
            env.cr.commit()
            _logger.info(f"Міграція завершена успішно. Перенесено {migrated_count} серійних номерів.")
            
        except Exception as e:
            _logger.error(f"Помилка під час міграції серійних номерів: {e}")
            env.cr.rollback()
            raise


def _parse_serial_numbers(serial_numbers_text):
    """
    Парсить текстове поле серійних номерів і повертає список унікальних номерів
    """
    if not serial_numbers_text:
        return []
    
    serials = []
    # Розділяємо по новому рядку, потім по комі
    for line in serial_numbers_text.split('\n'):
        for serial in line.split(','):
            serial = serial.strip()
            if serial and serial not in serials:  # Уникаємо дублікатів
                serials.append(serial)
    
    return serials
