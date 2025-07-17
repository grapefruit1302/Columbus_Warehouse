"""
Загальні утиліти для модуля custom_stock_receipt
"""
import logging

_logger = logging.getLogger(__name__)


def get_amount_in_words(amount):
    """Перетворює суму в слова українською мовою"""
    
    def get_currency_form(num):
        """Повертає правильну форму слова 'гривня'"""
        if num % 100 in [11, 12, 13, 14]:
            return "гривень"
        elif num % 10 == 1:
            return "гривня" 
        elif num % 10 in [2, 3, 4]:
            return "гривні"
        else:
            return "гривень"
    
    def get_kopeck_form(num):
        """Повертає правильну форму слова 'копійка'"""
        if num % 100 in [11, 12, 13, 14]:
            return "копійок"
        elif num % 10 == 1:
            return "копійка"
        elif num % 10 in [2, 3, 4]:
            return "копійки" 
        else:
            return "копійок"
    
    def convert_hundreds(num, feminine=False):
        """Конвертує число до 999 в слова"""
        ones = ['', 'один', 'два', 'три', 'чотири', "п'ять", 'шість', 'сім', 'вісім', "дев'ять"]
        ones_f = ['', 'одна', 'дві', 'три', 'чотири', "п'ять", 'шість', 'сім', 'вісім', "дев'ять"]
        teens = ['десять', 'одинадцять', 'дванадцять', 'тринадцять', 'чотирнадцять', 
                "п'ятнадцять", 'шістнадцять', 'сімнадцять', 'вісімнадцять', "дев'ятнадцять"]
        tens = ['', '', 'двадцять', 'тридцять', 'сорок', "п'ятдесят", 'шістдесят', 'сімдесят', 'вісімдесят', "дев'яносто"]
        hundreds = ['', 'сто', 'двісті', 'триста', 'чотириста', "п'ятсот", 'шістсот', 'сімсот', 'вісімсот', "дев'ятсот"]
        
        if num == 0:
            return ""
        
        result = []
        
        # Сотні
        if num >= 100:
            result.append(hundreds[num // 100])
            num %= 100
        
        # Десятки та одиниці
        if num >= 20:
            result.append(tens[num // 10])
            if num % 10 > 0:
                if feminine:
                    result.append(ones_f[num % 10])
                else:
                    result.append(ones[num % 10])
        elif num >= 10:
            result.append(teens[num - 10])
        elif num > 0:
            if feminine:
                result.append(ones_f[num])
            else:
                result.append(ones[num])
        
        return " ".join(result)
    
    def get_scale_word(num, words):
        """Повертає правильну форму масштабного слова"""
        if num % 100 in [11, 12, 13, 14]:
            return words[2]  # багато
        elif num % 10 == 1:
            return words[0]  # один
        elif num % 10 in [2, 3, 4]:
            return words[1]  # кілька
        else:
            return words[2]  # багато
    
    def number_to_words_ua(num):
        """Перетворює число в слова українською"""
        if num == 0:
            return "нуль"
        
        result = []
        
        # Мільярди
        if num >= 1000000000:
            billions = num // 1000000000
            result.append(convert_hundreds(billions))
            result.append(get_scale_word(billions, ['мільярд', 'мільярди', 'мільярдів']))
            num %= 1000000000
        
        # Мільйони
        if num >= 1000000:
            millions = num // 1000000
            result.append(convert_hundreds(millions))
            result.append(get_scale_word(millions, ['мільйон', 'мільйони', 'мільйонів']))
            num %= 1000000
        
        # Тисячі
        if num >= 1000:
            thousands = num // 1000
            result.append(convert_hundreds(thousands, True))  # жіночий рід для тисяч
            result.append(get_scale_word(thousands, ['тисяча', 'тисячі', 'тисяч']))
            num %= 1000
        
        # Сотні, десятки, одиниці (для гривень - жіночий рід)
        if num > 0:
            result.append(convert_hundreds(num, True))
        
        return " ".join(filter(None, result))
    
    try:
        int_part = int(amount)
        decimal_part = int(round((amount - int_part) * 100))
        
        if int_part == 0:
            words_part = "нуль"
        else:
            words_part = number_to_words_ua(int_part)
        
        currency_form = get_currency_form(int_part)
        
        if decimal_part == 0:
            return f"{words_part} {currency_form}"
        else:
            kopeck_words = number_to_words_ua(decimal_part) if decimal_part > 0 else "нуль"
            kopeck_form = get_kopeck_form(decimal_part)
            return f"{words_part} {currency_form} {kopeck_words} {kopeck_form}"
            
    except Exception as e:
        # Fallback з логуванням
        _logger.error(f"Error in get_amount_in_words: {e}")
        int_part = int(amount)
        decimal_part = int((amount - int_part) * 100)
        return f"{int_part} гривень {decimal_part:02d} копійок"


def get_company_prefix(company):
    """Отримує префікс компанії для нумерації документів"""
    if company and company.name:
        words = company.name.split()
        return words[1].upper()[:3] if len(words) >= 2 else words[0].upper()[:3] if words else 'XXX'
    return 'XXX'


def parse_serial_numbers(serial_numbers_text):
    """Розбирає текст з серійними номерами в список"""
    if not serial_numbers_text:
        return []
    
    serials = []
    for line_text in serial_numbers_text.split('\n'):
        for serial in line_text.split(','):
            serial = serial.strip()
            if serial:
                serials.append(serial)
    return serials


def format_serial_numbers(serials_list):
    """Форматує список серійних номерів в текст"""
    if not serials_list:
        return ""
    return '\n'.join(serials_list)


def validate_serial_numbers(env, serials_list, current_nomenclature_id, exclude_balance_ids=None):
    """Валідує серійні номери на унікальність в системі"""
    if not serials_list:
        return True, []
    
    exclude_balance_ids = exclude_balance_ids or []
    
    # Перевірка на дублікати в межах списку
    unique_serials = list(set(serials_list))
    if len(serials_list) != len(unique_serials):
        duplicates = [serial for serial in serials_list if serials_list.count(serial) > 1]
        return False, [f'Знайдено дублікати серійних номерів: {", ".join(set(duplicates))}']
    
    # Перевірка на існування в системі
    if env.get('stock.balance'):
        existing_serials = env['stock.balance'].search([
            ('serial_numbers', 'ilike', serials_list[0]),
            ('id', 'not in', exclude_balance_ids)
        ])
        
        conflicts = []
        for balance in existing_serials:
            if balance.serial_numbers:
                balance_serials = parse_serial_numbers(balance.serial_numbers)
                for serial in serials_list:
                    if serial in balance_serials and balance.nomenclature_id.id != current_nomenclature_id:
                        conflicts.append(f"{serial} (вже в {balance.nomenclature_id.name})")
        
        if conflicts:
            return False, [f'Серійні номери вже використовуються:\n{chr(10).join(conflicts)}']
    
    return True, []


def get_document_context_key(model_name):
    """Генерує ключ контексту для фільтрації компаній"""
    return f'_get_child_companies_domain,{model_name}'


def log_operation(operation_type, document_number, details=""):
    """Логує операцію"""
    _logger.info(f"📋 {operation_type}: {document_number} - {details}")


def format_posting_time_options(doc_date, today):
    """Форматує опції для часу проведення документа"""
    if doc_date == today:
        return [
            ('start_of_day', 'Початок дня'),
            ('end_of_day', 'Кінець дня'),
            ('current_time', 'Поточний час'),
            ('custom_time', 'Власний час')
        ]
    else:
        return [
            ('start_of_day', 'Початок вибраного дня'),
            ('end_of_day', 'Кінець вибраного дня')
        ]