# Pricelens: File Download Implementation Plan

> **Версия:** 3.0 (финальная)
> **Последнее обновление:** 4 августа 2025 г.

## 1. Цель

Сделать так, чтобы кнопка "Скачать исходный файл" на странице расследования (`/pricelens/investigate/<id>/`) работала, позволяя пользователям безопасно скачивать файлы, связанные с ошибками.

## 2. Проблема

В настоящее время сервис `consolidate_api` сохраняет файлы в защищенную системную директорию (`/root/failed_files/`). Веб-сервер Nginx, по соображениям безопасности, не имеет и не должен иметь доступа к этой директории. Из-за этого, когда `admin2` генерирует ссылку на скачивание, Nginx не может найти файл и возвращает ошибку 404 (Not Found).

## 3. План решения

Решение состоит из нескольких частей: создание общей директории на сервере, настройка `docker-compose.yml` в обоих проектах для доступа к этой директории, изменение логики сохранения файлов в `consolidate_api`, исправление логики логирования пути и, наконец, настройка Nginx в `admin2`.

---

## 4. Пошаговая инструкция

### Шаг 1: Создание общей директории на сервере

Эту команду нужно выполнить на вашем сервере `87.242.110.159` один раз.

```bash
sudo mkdir -p /var/www/failed_files/
sudo chown -R www-data:www-data /var/www/failed_files/
```

### Шаг 2: Изменение кода в `consolidate_api` (Путь сохранения)

**Файл для редактирования:** `C:\torgzap\github_repos\consolidate_api\file_service\file_manipulation.py`

**Найдите функцию:** `save_failed_file`

**Замените этот код:**
```python
save_dir = Path(f"/root/failed_files/{supid}/")
```

**На этот код:**
```python
save_dir = Path(f"/var/www/failed_files/{supid}/")
```

### Шаг 3: Настройка Docker Compose

**A. Для `consolidate_api`:**

**Файл:** `C:\torgzap\github_repos\consolidate_api\docker-compose.yml`

**Замените этот блок:**
```yaml
    volumes:
      - ./logs:/app/logs
      - /root/failed_files:/root/failed_files
      # ... другие volumes
```

**На этот блок:**
```yaml
    volumes:
      - ./logs:/app/logs
      - /var/www/failed_files:/var/www/failed_files
      # ... другие volumes
```

**B. Для `admin2`:**

**Файл:** `C:\torgzap\github_repos\admin2\docker-compose.yml`

**Найдите сервис `frontend-proxy` и добавьте ему новый volume:**
```yaml
  frontend-proxy:
    # ... image, ports ...
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - admin2_static_data:/static:ro
      - admin2_media_data:/media:ro
      # ДОБАВЬТЕ ЭТУ СТРОКУ
      - /var/www/failed_files:/var/www/failed_files:ro
    # ... depends_on ...
```

### Шаг 4: Настройка Nginx в проекте `admin2`

**Файл:** `C:\torgzap\github_repos\admin2\nginx.conf`

Добавьте новый `location` блок в секцию `server`:

```nginx
       location /failed_files/ {
           alias /var/www/failed_files/;
           autoindex off;
       }
```

### Шаг 5: Корректировка логики логирования в `consolidate_api`

**Это критически важный шаг.** Сейчас `consolidate_api` логирует временный путь к файлу, а не конечный. Нужно это исправить.

**Файл для редактирования:** `C:\torgzap\github_repos\consolidate_api\file_service\file_reader.py`

Вам нужно найти **все** блоки `except`, где вызываются `log_event_to_pricelens` и `save_failed_file`. Это касается функций `csv_reader` и `exel_reader`.

**Найдите и замените этот паттерн:**
```python
# Старый код (НЕПРАВИЛЬНЫЙ)
except Exception as e:
    # ... (код для логов и сообщений в чат)
    log_event_to_pricelens(supid=supid, reason=reason, stage="consolidate", file_path=file_path)
    save_failed_file(supid, file_path, reason)
```

**На этот новый паттерн:**
```python
# Новый код (ПРАВИЛЬНЫЙ)
except Exception as e:
    # ... (код для логов и сообщений в чат)
    new_file_path = save_failed_file(supid, file_path, reason)
    log_event_to_pricelens(supid=supid, reason=reason, stage="consolidate", file_path=new_file_path)
```

### Шаг 6: Обновление `file_path` в `admin2` (API вызов)

В `log_event_to_pricelens` в `consolidate_api` нужно изменить передаваемый `file_path`, чтобы он был относительным.

**Найдите функцию:** `log_event_to_pricelens`

**Замените этот код:**
```python
"file_path": str(file_path)
```

**На этот код:**
```python
"file_path": str(file_path).replace("/var/www/", "")
```

### Шаг 7: Перезапуск и Проверка

1.  **Перезапустите оба сервиса**, чтобы все изменения применились.
2.  **Проверьте** работоспособность с помощью `curl`:

```bash
curl -X POST http://87.242.110.159/api/v1/pricelens/log_event/ \
-H "Authorization: Token <your_token>" \
-H "Content-Type: application/json" \
-d '{
    "event_dt": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'",
    "supid": 9998,
    "reason": "DOWNLOAD_TEST",
    "stage": "curl_test",
    "file_path": "failed_files/9998/test_file.txt"
}'
```

После этого в интерфейсе `admin2` должна появиться ссылка на скачивание, которая будет работать.