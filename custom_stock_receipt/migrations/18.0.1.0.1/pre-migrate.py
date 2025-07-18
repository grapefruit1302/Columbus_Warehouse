def migrate(cr, version):
    """Видаляємо стару таблицю/view stock_receipt_documents_line перед створенням нового view"""
    
    # Видаляємо view якщо він існує
    cr.execute("DROP VIEW IF EXISTS stock_receipt_documents_line CASCADE")
    
    # Видаляємо таблицю якщо вона існує
    cr.execute("DROP TABLE IF EXISTS stock_receipt_documents_line CASCADE")