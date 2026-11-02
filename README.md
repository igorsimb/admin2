# Admin2

> Django-проект для администрирования

## Начало работы

### Предварительные требования

- Python 3.14 (Docker использует 3.14.8)
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
uv python install 3.14
uv venv --python 3.14

# Активация виртуального окружения
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# Установка зависимостей для разработки
uv sync --locked --all-groups

# (При необходимости) Не устанавливать зависимости для разработки
uv sync --locked --no-dev

# Настройка базы данных
uv run manage.py migrate

# Запуск сервера разработки
uv run manage.py runserver
```

### Управление зависимостями

Проект использует `uv`; точные версии для Windows и Linux зафиксированы в `uv.lock`.
Основные команды:

- `uv sync --locked` - установка основных зависимостей и группы dev по lock-файлу
- `uv sync --locked --all-groups` - установка всех групп зависимостей
- `uv sync --locked --no-dev` - установка без инструментов разработки
- `uv lock --upgrade --python 3.14` - обновление до последних совместимых версий; после этого нужны тесты
- `uv export --locked --no-dev --format requirements-txt --output-file requirements.txt` - обновление экспорта для pip

Не обновляйте `requirements.txt` отдельно от `uv.lock`. После изменения зависимостей проверьте
`uv run pytest -n 0` и соберите Docker-образ. Текущий lock-файл использует Django 6.0.9:
`django-celery-beat` 2.9.0 ограничивает Django версией `<6.1`.

При переходе с Python 3.12 удалите старую `.venv` и создайте её заново командами выше.
Перед запуском обновлённого приложения примените миграции в нужном окружении.

### Docker

Образ устанавливает зависимости через `uv sync --locked --no-dev`. Окружение находится
в `/opt/venv`, поэтому подключение исходников в `/app` через Compose не скрывает зависимости.
Python и uv закреплены в `Dockerfile`; файл `requirements.txt` при сборке не используется.

Для проверки с инструментами разработки:

```bash
docker build --build-arg INSTALL_DEV=true -t admin2:check .
docker run --rm --network none -e DJANGO_SECRET_KEY=local-test-key -e DJANGO_SETTINGS_MODULE=config.django_config.test admin2:check python -m pytest -n 0
```

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

---

### ✅ Использование pre-commit

Для автоматической проверки и форматирования кода перед каждым коммитом используем [pre-commit](https://pre-commit.com/).

#### Установка хуков:

```bash
pre-commit install
```

Эта команда настроит Git-хук, который будет запускать проверки при каждом коммите.

#### Ручной запуск всех проверок:

```bash
pre-commit run --all-files
```

Полезно для запуска всех хуков сразу, например, после клонирования проекта или перед пушем.


### Структура проекта

Проект организован в соответствии с принципами модульных Django-приложений:

- `core` - базовые компоненты и утилиты
- `accounts` - управление пользователями и аутентификация
- `cross_dock` - модуль для отчета по кросс-доку
