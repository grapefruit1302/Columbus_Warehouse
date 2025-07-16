"""
Сервіс для роботи з валютою та конвертації сум у слова
"""


class CurrencyService:
    """Сервіс для роботи з валютою"""
    
    @staticmethod
    def amount_to_words_ua(amount):
        """Перетворює суму в слова українською мовою
        
        Args:
            amount (float): Сума для конвертації
            
        Returns:
            str: Сума прописом українською
        """
        if not amount:
            return "нуль гривень 00 копійок"
        
        def get_currency_form(number):
            """Повертає правильну форму слова 'гривня'"""
            if number % 100 in [11, 12, 13, 14]:
                return 'гривень'
            elif number % 10 == 1:
                return 'гривня'
            elif number % 10 in [2, 3, 4]:
                return 'гривні'
            else:
                return 'гривень'
        
        def get_kopeck_form(number):
            """Повертає правильну форму слова 'копійка'"""
            if number % 100 in [11, 12, 13, 14]:
                return 'копійок'
            elif number % 10 == 1:
                return 'копійка'
            elif number % 10 in [2, 3, 4]:
                return 'копійки'
            else:
                return 'копійок'
        
        def convert_hundreds(number):
            """Конвертує число від 0 до 999 в слова"""
            ones = ['', 'один', 'два', 'три', 'чотири', "п'ять", 'шість', 'сім', 'вісім', "дев'ять"]
            teens = ['десять', 'одинадцять', 'дванадцять', 'тринадцять', 'чотирнадцять', 
                    "п'ятнадцять", 'шістнадцять', 'сімнадцять', 'вісімнадцять', "дев'ятнадцять"]
            tens = ['', '', 'двадцять', 'тридцять', 'сорок', "п'ятдесят", 'шістдесят', 
                   'сімдесят', 'вісімдесят', "дев'яносто"]
            hundreds = ['', 'сто', 'двісті', 'триста', 'чотириста', "п'ятсот", 'шістсот', 
                       'сімсот', 'вісімсот', "дев'ятсот"]
            
            result = []
            
            # Сотні
            h = number // 100
            if h > 0:
                result.append(hundreds[h])
            
            # Десятки та одиниці
            remainder = number % 100
            if remainder >= 10 and remainder < 20:
                result.append(teens[remainder - 10])
            else:
                t = remainder // 10
                o = remainder % 10
                if t > 0:
                    result.append(tens[t])
                if o > 0:
                    result.append(ones[o])
            
            return ' '.join(result)
        
        def get_scale_word(number, scale):
            """Повертає правильну форму слова для розряду (тисяча, мільйон тощо)"""
            if scale == 1:  # тисячі
                if number % 100 in [11, 12, 13, 14]:
                    return 'тисяч'
                elif number % 10 == 1:
                    return 'тисяча'
                elif number % 10 in [2, 3, 4]:
                    return 'тисячі'
                else:
                    return 'тисяч'
            elif scale == 2:  # мільйони
                if number % 100 in [11, 12, 13, 14]:
                    return 'мільйонів'
                elif number % 10 == 1:
                    return 'мільйон'
                elif number % 10 in [2, 3, 4]:
                    return 'мільйони'
                else:
                    return 'мільйонів'
            return ''
        
        def number_to_words_ua(number):
            """Конвертує ціле число в слова"""
            if number == 0:
                return 'нуль'
            
            groups = []
            while number > 0:
                groups.append(number % 1000)
                number //= 1000
            
            result = []
            for i, group in enumerate(reversed(groups)):
                if group == 0:
                    continue
                
                scale = len(groups) - 1 - i
                group_words = convert_hundreds(group)
                
                if scale == 1:
                    group_words = group_words.replace('один', 'одна').replace('два', 'дві')
                
                if group_words:
                    result.append(group_words)
                    if scale > 0:
                        result.append(get_scale_word(group, scale))
            
            return ' '.join(result)
        
        hryvnias = int(amount)
        kopecks = int(round((amount - hryvnias) * 100))
        
        hryvnia_words = number_to_words_ua(hryvnias)
        currency_form = get_currency_form(hryvnias)
        kopeck_form = get_kopeck_form(kopecks)
        
        return f"{hryvnia_words} {currency_form} {kopecks:02d} {kopeck_form}"
    
    @staticmethod
    def format_currency(amount, currency_code='UAH'):
        """Форматує суму з валютою
        
        Args:
            amount (float): Сума
            currency_code (str): Код валюти
            
        Returns:
            str: Відформатована сума
        """
        if currency_code == 'UAH':
            return f"{amount:.2f} грн."
        else:
            return f"{amount:.2f} {currency_code}"
    
    @staticmethod
    def calculate_vat(amount_no_vat, vat_rate):
        """Розраховує ПДВ
        
        Args:
            amount_no_vat (float): Сума без ПДВ
            vat_rate (float): Ставка ПДВ у відсотках
            
        Returns:
            tuple: (сума ПДВ, сума з ПДВ)
        """
        vat_amount = amount_no_vat * (vat_rate / 100)
        amount_with_vat = amount_no_vat + vat_amount
        return vat_amount, amount_with_vat
    
    @staticmethod
    def calculate_amount_no_vat(amount_with_vat, vat_rate):
        """Розраховує суму без ПДВ з суми з ПДВ
        
        Args:
            amount_with_vat (float): Сума з ПДВ
            vat_rate (float): Ставка ПДВ у відсотках
            
        Returns:
            tuple: (сума без ПДВ, сума ПДВ)
        """
        amount_no_vat = amount_with_vat / (1 + vat_rate / 100)
        vat_amount = amount_with_vat - amount_no_vat
        return amount_no_vat, vat_amount
