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

### Рабочий процесс разработки с несколькими окружениями

Проект поддерживает два окружения: `staging` (разработка) и `production` (продакшн). Каждое окружение имеет свои настройки и подключается к разным базам данных.

#### Настройка окружений

1. Создайте файлы `.env.staging` и `.env.production` на основе `.env.example`:

```
# .env.staging
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=True
DJANGO_ENVIRONMENT=staging
STAGING_CLICKHOUSE_HOST=staging_ip
STAGING_CLICKHOUSE_USER=staging_user
STAGING_CLICKHOUSE_PASSWORD=staging_password
```

```
# .env.production
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=False
DJANGO_ENVIRONMENT=production
PROD_CLICKHOUSE_HOST=prod_ip
PROD_CLICKHOUSE_USER=prod_user
PROD_CLICKHOUSE_PASSWORD=prod_password
```

2. Добавьте функцию `setdjangoenv` в ваш PowerShell профиль (см. `docs/commands.md`).

#### Процесс разработки

1. **Разработка в окружении staging**:
   ```powershell
   # Переключение на окружение staging
   setdjangoenv staging

   # Разработка и тестирование в staging
   uv run manage.py runserver
   ```

2. **Тестирование в окружении production**:
   ```powershell
   # Переключение на окружение production
   setdjangoenv production

   # Тестирование в production
   uv run manage.py runserver
   ```

3. **Работа с миграциями базы данных**:
   ```powershell
   # Создание миграций в staging
   setdjangoenv staging
   uv run manage.py makemigrations

   # Применение миграций в staging
   uv run manage.py migrate

   # Применение миграций в production (после тестирования в staging)
   setdjangoenv production
   uv run manage.py migrate
   ```

Этот подход позволяет безопасно разрабатывать и тестировать функциональность в окружении staging, прежде чем применять изменения в production.

### Структура проекта

Проект организован в соответствии с принципами модульных Django-приложений:

- `core` - базовые компоненты и утилиты
- `accounts` - управление пользователями и аутентификация
