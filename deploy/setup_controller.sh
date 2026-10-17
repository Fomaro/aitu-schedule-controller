#!/usr/bin/env bash
# ==============================================================================
# Скрипт автоматической установки AITU Schedule Controller на VPS (Ubuntu/Debian)
# ==============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=====================================================================${NC}"
echo -e "${BLUE}   👑 Установка AITU Schedule Controller (Supervisor) на VPS         ${NC}"
echo -e "${BLUE}=====================================================================${NC}"

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Пожалуйста, запустите скрипт от root (или sudo bash deploy/setup_controller.sh)${NC}"
    exit 1
fi

INSTALL_DIR="/opt/aitu-schedule-controller"
REPO_URL="https://github.com/Fomaro/aitu-schedule-controller.git"

echo -e "\n${YELLOW}1. Обновление пакетов и установка зависимостей...${NC}"
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git curl htop

echo -e "\n${YELLOW}2. Настройка рабочей директории: ${INSTALL_DIR}...${NC}"
if [ -d "$INSTALL_DIR/.git" ]; then
    echo -e "${GREEN}Репозиторий уже существует. Обновляем кодовую базу...${NC}"
    cd "$INSTALL_DIR"
    git fetch origin main
    git reset --hard origin/main
else
    echo -e "${GREEN}Клонируем репозиторий в ${INSTALL_DIR}...${NC}"
    mkdir -p "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo -e "\n${YELLOW}3. Создание виртуального окружения (venv)...${NC}"
if [ ! -d "$INSTALL_DIR/venv" ]; then
    python3 -m venv "$INSTALL_DIR/venv"
fi

echo -e "\n${YELLOW}4. Установка Python зависимостей...${NC}"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

echo -e "\n${YELLOW}5. Проверка файла конфигурации .env...${NC}"
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo -e "${YELLOW}⚠️ Файл .env был создан из шаблона!${NC}"
    echo -e "${YELLOW}ОБЯЗАТЕЛЬНО укажите CONTROLLER_BOT_TOKEN и SUPERADMIN_IDS в ${INSTALL_DIR}/.env${NC}"
    echo -e "${YELLOW}Команда: nano ${INSTALL_DIR}/.env${NC}"
fi

echo -e "\n${YELLOW}6. Установка Systemd службы aitu-controller.service...${NC}"
cp "$INSTALL_DIR/deploy/aitu-controller.service" /etc/systemd/system/aitu-controller.service
systemctl daemon-reload
systemctl enable aitu-controller.service

# Создаем скрипт быстрого ручного обновления
cat << 'EOF' > "$INSTALL_DIR/deploy/update.sh"
#!/usr/bin/env bash
set -e
echo "🔄 Обновление контроллера из Git..."
cd /opt/aitu-schedule-controller
git fetch origin main
git reset --hard origin/main
./venv/bin/pip install -r requirements.txt --quiet
systemctl restart aitu-controller
echo "✅ Бот-контроллер успешно обновлен и перезапущен!"
systemctl status aitu-controller --no-pager
EOF
chmod +x "$INSTALL_DIR/deploy/update.sh"

echo -e "\n${YELLOW}7. Запуск службы aitu-controller...${NC}"
systemctl restart aitu-controller.service
sleep 2

if systemctl is-active --quiet aitu-controller.service; then
    echo -e "\n${GREEN}=====================================================================${NC}"
    echo -e "${GREEN}   ✅ Бот-контроллер успешно запущен и работает в фоне!             ${NC}"
    echo -e "${GREEN}=====================================================================${NC}"
else
    echo -e "\n${YELLOW}⚠️ Служба создана, но проверьте токен в .env файле:${NC}"
    echo -e "1) Откройте: nano ${INSTALL_DIR}/.env"
    echo -e "2) Вставьте токен бота CONTROLLER_BOT_TOKEN от @BotFather"
    echo -e "3) Перезапустите: systemctl restart aitu-controller"
fi

echo -e "\n${BLUE}Полезные команды для управления контроллером:${NC}"
echo -e "  Статус:        ${GREEN}systemctl status aitu-controller${NC}"
echo -e "  Логи онлайн:   ${GREEN}journalctl -u aitu-controller -f${NC}"
echo -e "  Перезапуск:    ${GREEN}systemctl restart aitu-controller${NC}"
echo -e "  Обновить код:  ${GREEN}/opt/aitu-schedule-controller/deploy/update.sh${NC}"
