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
