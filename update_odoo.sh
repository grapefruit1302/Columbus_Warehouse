#!/bin/bash

# Змінні
VENV_PATH="/opt/odoo18/odoo18-venv"
ODOO_PATH="/opt/odoo18/odoo18"
CONFIG_FILE="/etc/odoo18.conf"
DATABASE_NAME="Odoo4"
TEMP_CONFIG="/tmp/odoo18_temp.conf"

# Кольори
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%H:%M:%S')] ERROR: $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')] WARNING: $1${NC}"
}

# Перевірка sudo
if ! sudo -n true 2>/dev/null; then
    echo "Введіть пароль sudo:"
    sudo -v || exit 1
fi

# Перевірка файлів
if [ ! -f "$ODOO_PATH/odoo-bin" ]; then
    error "odoo-bin не знайдено"
    exit 1
fi

if [ ! -f "$VENV_PATH/bin/python3" ]; then
    error "Python віртуальне середовище не знайдено"
    exit 1
fi

# Перевірка підключення до БД
log "Перевірка підключення до бази $DATABASE_NAME..."
if ! sudo -u odoo18 psql -d "$DATABASE_NAME" -c "SELECT 1;" > /dev/null 2>&1; then
    error "Не можу підключитися до бази $DATABASE_NAME"
    exit 1
fi
log "Підключення до бази успішне"

# Запит модуля
echo
echo "Введіть назву модуля для оновлення (або 'all' для всіх):"
read -r MODULE_NAME

if [ -z "$MODULE_NAME" ]; then
    error "Модуль не вказано"
    exit 1
fi

log "Буде оновлено: $MODULE_NAME"

# Зупинка сервісу
log "Зупинка Odoo..."
sudo systemctl stop odoo18
sleep 3

if systemctl is-active --quiet odoo18; then
    error "Не вдалося зупинити Odoo"
    exit 1
fi

# Створення тимчасового конфігу
log "Створення тимчасового конфігу..."
sudo cp "$CONFIG_FILE" "$TEMP_CONFIG"
echo "db_name = $DATABASE_NAME" | sudo tee -a "$TEMP_CONFIG" > /dev/null
sudo chmod 644 "$TEMP_CONFIG"

# Активація віртуального середовища
log "Активація віртуального середовища..."
source "$VENV_PATH/bin/activate"

if [ -z "$VIRTUAL_ENV" ]; then
    error "Не вдалося активувати віртуальне середовище"
    sudo rm -f "$TEMP_CONFIG"
    exit 1
fi

# Оновлення модуля
log "Оновлення модуля $MODULE_NAME..."
log "База даних: $DATABASE_NAME"

echo
echo "Команда що виконується:"
if [ "$MODULE_NAME" = "all" ]; then
    echo "$VENV_PATH/bin/python3 $ODOO_PATH/odoo-bin --config=$TEMP_CONFIG -u all --stop-after-init --no-http"
    "$VENV_PATH/bin/python3" "$ODOO_PATH/odoo-bin" --config="$TEMP_CONFIG" -u all --stop-after-init --no-http
else
    echo "$VENV_PATH/bin/python3 $ODOO_PATH/odoo-bin --config=$TEMP_CONFIG -u $MODULE_NAME --stop-after-init --no-http"
    "$VENV_PATH/bin/python3" "$ODOO_PATH/odoo-bin" --config="$TEMP_CONFIG" -u "$MODULE_NAME" --stop-after-init --no-http
fi

UPDATE_RESULT=$?

# Очищення
deactivate
sudo rm -f "$TEMP_CONFIG"

# Перевірка результату
if [ $UPDATE_RESULT -eq 0 ]; then
    log "Оновлення завершено успішно!"
else
    error "Помилка оновлення (код: $UPDATE_RESULT)"
fi

# Запуск сервісу
log "Запуск Odoo..."
sudo systemctl start odoo18
sleep 5

if systemctl is-active --quiet odoo18; then
    log "Odoo запущено успішно!"
    log "Доступ: http://localhost:8069"
else
    error "Не вдалося запустити Odoo"
    warn "Перевірте логи: sudo journalctl -u odoo18 -f"
    exit 1
fi

if [ $UPDATE_RESULT -eq 0 ]; then
    log "Скрипт завершено успішно!"
else
    error "Скрипт завершено з помилками"
    exit 1
fi