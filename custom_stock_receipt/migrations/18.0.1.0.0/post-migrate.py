def migrate(cr, version):
    """Створюємо індекси для оптимізації роботи з документами"""
    
    # Індекси для прихідних накладних
    cr.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_receipt_incoming_date 
        ON stock_receipt_incoming (date);
    """)
    
    cr.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_receipt_incoming_state 
        ON stock_receipt_incoming (state);
    """)
    
    cr.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_receipt_incoming_partner 
        ON stock_receipt_incoming (partner_id);
    """)
    
    # Індекси для актів оприходування
    cr.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_receipt_disposal_date 
        ON stock_receipt_disposal (date);
    """)
    
    cr.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_receipt_disposal_state 
        ON stock_receipt_disposal (state);
    """)
    
    # Індекси для повернень з сервісу (якщо таблиця існує)
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'stock_receipt_return'
        );
    """)
    if cr.fetchone()[0]:
        cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_stock_receipt_return_date 
            ON stock_receipt_return (date);
        """)
        
        cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_stock_receipt_return_state 
            ON stock_receipt_return (state);
        """)
    
    # Індекси для рядків документів
    cr.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_receipt_incoming_line_receipt_id 
        ON stock_receipt_incoming_line (receipt_id);
    """)
    
    cr.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_receipt_disposal_line_disposal_id 
        ON stock_receipt_disposal_line (disposal_id);
    """)
    
    # Індекси для рядків повернень (якщо таблиця існує)
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'stock_receipt_return_line'
        );
    """)
    if cr.fetchone()[0]:
        cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_stock_receipt_return_line_return_id 
            ON stock_receipt_return_line (return_id);
        """)