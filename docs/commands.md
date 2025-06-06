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
