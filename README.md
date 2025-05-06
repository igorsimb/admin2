# Admin2

> Django-проект для администрирования

## Начало работы

### Предварительные требования

- Python 3.12 или выше
- Git

### Установка и настройка

```bash
# Клонирование репозитория
git clone https://github.com/your-username/admin2.git
cd admin2

# Установка uv
# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Создание виртуального окружения
uv venv

# Активация виртуального окружения
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# Установка зависимостей для разработки
uv sync --all-groups

# Настройка базы данных
uv run manage.py migrate

# Запуск сервера разработки
uv run manage.py runserver
```

### Управление зависимостями

Проект использует `uv` для управления зависимостями. Основные команды:

- `uv sync` - установка только основных зависимостей
- `uv sync --all-groups` - установка всех зависимостей, включая инструменты разработки
- `uv sync --group dev` - установка основных зависимостей и группы dev

### Структура проекта

Проект организован в соответствии с принципами модульных Django-приложений:

- `core` - базовые компоненты и утилиты
- `accounts` - управление пользователями и аутентификация
