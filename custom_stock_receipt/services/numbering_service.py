"""
Сервіс для генерації номерів документів
"""
from odoo import api


class NumberingService:
    """Сервіс для роботи з нумерацією документів"""
    
    @staticmethod
    def generate_receipt_number(receipt_type, env):
        """Генерує номер документа
        
        Args:
            receipt_type (str): Тип документа ('incoming', 'disposal', 'return')
            env: Odoo environment
            
        Returns:
            str: Згенерований номер документа
        """
        sequence_codes = {
            'incoming': 'stock.receipt.incoming',
            'disposal': 'stock.receipt.disposal', 
            'return': 'stock.receipt.return'
        }
        
        sequence_code = sequence_codes.get(receipt_type)
        if not sequence_code:
            raise ValueError(f"Unknown receipt type: {receipt_type}")
        
        return env['ir.sequence'].next_by_code(sequence_code) or 'Новий'
    
    @staticmethod
    def ensure_sequence_exists(receipt_type, env):
        """Перевіряє та створює послідовність якщо не існує
        
        Args:
            receipt_type (str): Тип документа
            env: Odoo environment
            
        Returns:
            bool: True якщо послідовність існує або була створена
        """
        sequence_codes = {
            'incoming': 'stock.receipt.incoming',
            'disposal': 'stock.receipt.disposal',
            'return': 'stock.receipt.return'
        }
        
        sequence_names = {
            'incoming': 'Прихідні накладні',
            'disposal': 'Акти оприходування',
            'return': 'Повернення з сервісу'
        }
        
        sequence_code = sequence_codes.get(receipt_type)
        sequence_name = sequence_names.get(receipt_type)
        
        if not sequence_code or not sequence_name:
            return False
        
        existing = env['ir.sequence'].search([('code', '=', sequence_code)], limit=1)
        if existing:
            return True
        
        try:
            env['ir.sequence'].create({
                'name': sequence_name,
                'code': sequence_code,
                'prefix': f"{receipt_type.upper()}/",
                'suffix': '',
                'padding': 4,
                'number_increment': 1,
                'number_next': 1,
                'implementation': 'standard',
            })
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_next_number_preview(receipt_type, env):
        """Показує наступний номер без його використання
        
        Args:
            receipt_type (str): Тип документа
            env: Odoo environment
            
        Returns:
            str: Наступний номер документа
        """
        sequence_codes = {
            'incoming': 'stock.receipt.incoming',
            'disposal': 'stock.receipt.disposal',
            'return': 'stock.receipt.return'
        }
        
        sequence_code = sequence_codes.get(receipt_type)
        if not sequence_code:
            return 'Невідомий тип'
        
        sequence = env['ir.sequence'].search([('code', '=', sequence_code)], limit=1)
        if not sequence:
            return 'Послідовність не знайдена'
        
        return sequence._get_prefix_suffix()[0] + str(sequence.number_next).zfill(sequence.padding) + sequence._get_prefix_suffix()[1]
