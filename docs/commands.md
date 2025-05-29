# Команды проекта

## Управление Django с помощью uv

### Базовое использование

```bash
# Вместо python manage.py используйте
uv run manage.py <команда>

# Примеры
uv run manage.py runserver
uv run manage.py migrate
uv run manage.py createsuperuser
```

### Pre-commit
```bash
pre-commit install
```
```bash
pre-commit run --all-files
```

### Создание алиаса в PowerShell

Добавьте в ваш PowerShell профиль ($profile):

```powershell
function uvm {
    param(
        [Parameter(ValueFromRemainingArguments=$true)]
        [string[]]$Args
    )
    uv run manage.py @Args
}
```

Теперь можно использовать:

```powershell
uvm runserver
uvm migrate
uvm createsuperuser
```

## Переключение между окружениями

### Функция для переключения окружений

Добавьте в ваш PowerShell профиль ($profile):

```powershell
function setdjangoenv {
    param (
        [Parameter(Mandatory=$true)]
        [ValidateSet("staging", "production")]
        [string]$Environment
    )

    # Set the environment variable
    $env:DJANGO_ENVIRONMENT = $Environment

    # Copy the appropriate .env file to .env
    Copy-Item -Path ".env.$Environment" -Destination ".env" -Force

    Write-Host "Django environment set to: $Environment"
    Write-Host ".env.$Environment copied to .env"
}
```

### Использование функции переключения окружений

```powershell
# Переключение на окружение staging
setdjangoenv staging

# Запуск Django с окружением staging
uv run manage.py runserver

# Переключение на окружение production
setdjangoenv production

# Запуск Django с окружением production
uv run manage.py runserver
```

## Использование Ruff

### Проверка кода

```bash
# Проверка всего проекта
ruff check .

# Проверка конкретного файла
ruff check path/to/file.py

# Проверка директории
ruff check path/to/directory/
```

### Автоматическое исправление

```bash
# Исправление всего проекта
ruff check --fix .

# Исправление конкретного файла
ruff check --fix path/to/file.py
```

### Форматирование кода

```bash
# Форматирование всего проекта
ruff format .

# Форматирование конкретного файла
ruff format path/to/file.py

# Форматирование директории
ruff format path/to/directory/
```

### Проверка без внесения изменений

```bash
# Проверка форматирования без внесения изменений
ruff format --check .

# Проверка линтинга без внесения изменений
ruff check --no-fix .
```

### Проверка связи с ClickHouse

```bash
uvm test_ch_con
```
В случае успешной проверки вывод будет вида:
```
Testing ClickHouse connection...
Connection successful! Result: [(1,)]
ClickHouse version: 25.1.4.53
Connection test completed successfully
```
В случае неудачной проверки вывод будет вида:
```
Testing ClickHouse connection...
socket.gaierror: [Errno 11001] getaddrinfo failed
ERROR:cross_dock.services.clickhouse_service:Error during ClickHouse operation: Code: 210. getaddrinfo failed (111)
```

---

## Управление проектом с помощью Docker Compose

Управление происходит через `docker-compose`. У нас есть отдельные файлы для `staging` и `production` окружений.

### Переключение между окружениями

Для переключения окружений указывайте нужный файл `docker-compose` и `.env` файл будет автоматически подтянут.

### Сборка и запуск Docker образов

Перед первым запуском или после изменений в `Dockerfile` или зависимостях (`pyproject.toml`, `uv.lock`), необходимо собрать образы.

```bash
# Сборка образов для staging
docker-compose -f docker-compose.staging.yml build

# Сборка образов для production
docker-compose -f docker-compose.production.yml build
```

### Запуск сервисов

Для запуска всех сервисов (Django, Celery, Redis, Nginx, PostgreSQL в production) в фоновом режиме:

```bash
# Запуск сервисов staging
docker-compose -f docker-compose.staging.yml up -d

# Запуск сервисов production
docker-compose -f docker-compose.production.yml up -d
```

### Остановка сервисов

Для остановки всех сервисов, запущенных через Docker Compose:

```bash
# Остановка сервисов staging
docker-compose -f docker-compose.staging.yml down

# Остановка сервисов production
docker-compose -f docker-compose.production.yml down
```

### Выполнение команд внутри контейнера (Разработка)

При разработке в контейнере `staging`, вам может понадобиться выполнять Django команды (`manage.py`) или другие утилиты (`uv run`). Используйте `docker-compose exec` для этого. Команды выполняются внутри запущенного контейнера сервиса `django`.

```bash
# Пример: Выполнение миграций
docker-compose -f docker-compose.staging.yml exec django uv run manage.py migrate

# Пример: Создание суперпользователя
docker-compose -f docker-compose.staging.yml exec django uv run manage.py createsuperuser

# Пример: Запуск тестов
docker-compose -f docker-compose.staging.yml exec django uv run pytest

# Пример: Проверка подключения к ClickHouse (как определено в commands.md)
docker-compose -f docker-compose.staging.yml exec django uv run manage.py test_ch_con
```

Для production, выполнение таких команд обычно делается как часть процесса деплоя (например, в CI/CD пайплайне или скрипте), но синтаксис будет аналогичным, просто с использованием `docker-compose.production.yml`.

### Просмотр логов

Для просмотра логов всех сервисов или конкретного сервиса:

```bash
# Просмотр логов всех сервисов (staging)
docker-compose -f docker-compose.staging.yml logs -f

# Просмотр логов конкретного сервиса (например, django в staging)
docker-compose -f docker-compose.staging.yml logs -f django

# Просмотр логов всех сервисов (production)
docker-compose -f docker-compose.production.yml logs -f

# Просмотр логов конкретного сервиса (например, nginx в production)
docker-compose -f docker-compose.production.yml logs -f nginx
```

---