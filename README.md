# AI Generation Microservice

Микросервис для генерации изображений и видео с использованием Fal.ai API (модель WAN 2.5).

## Возможности

- **4 типа генерации**: text-to-image, image-to-image, text-to-video, image-to-video
- **Система пользователей** с балансом в условных токенах
- **Интеграция со Stripe** — пополнение баланса через Stripe Checkout / PaymentIntent
- **Асинхронная обработка** генераций через Celery + Redis
- **Жизненный цикл задач**: `created -> queued -> processing -> completed / failed`
- **Пополнение баланса** через входящие webhook (Stripe / пользовательский)
- **Возврат токенов** при ошибках генерации
- **Доставка webhook-уведомлений** клиенту (5 попыток, интервал 15 сек)
- **Rate limiting**: 10 запросов/мин, блокировка на 60 сек при превышении
- **Метрики Prometheus**: количество генераций, ошибки, себестоимость, API-запросы
- **Логирование** в JSON-формате с ротацией 7 дней
- **Circuit breaker** для автоматического переключения на fallback-провайдера
- **Проксированное скачивание** результатов генерации
- **Ngrok-туннель** для разработки (отдельный docker-compose)

## Технологии

- Python 3.11, FastAPI, Uvicorn
- PostgreSQL 15, SQLAlchemy 2.0 (async), Alembic
- Celery 5, Redis 7
- Stripe (webhook-интеграция)
- fal-client (Fal.ai SDK)
- Prometheus
- Ruff (линтер + форматер)
- Docker, Docker Compose

## Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone <repo-url>
cd ai-generator
```

### 2. Настроить переменные окружения

```bash
cp .env.example .env
```

Отредактируйте `.env` и укажите:
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` — подключение к PostgreSQL
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASS` — подключение к Redis
- `FAL_KEY` — API-ключ Fal.ai (https://fal.ai/dashboard/keys)
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` — ключи Stripe
- `FAL_WEBHOOK_BASE_URL` — публичный URL сервиса (для получения webhook от Fal.ai и Stripe)

### 3. Запустить через Docker Compose

```bash
docker compose up -d --build
```

Сервисы:
| Сервис | Порт | Описание |
|---|---|---|
| app | 8000 | FastAPI API |
| celery-worker | — | Фоновая обработка генераций |
| postgres | 5432 | PostgreSQL |
| redis | 6379 | Redis |
| prometheus | 9090 | Метрики |

### 4. Запуск с ngrok (для разработки)

Для получения публичного URL (webhook-ы от Stripe/Fal.ai) используйте дополнительный compose-файл:

```bash
docker compose -f docker-compose.yml -f docker-compose.ngrok.yml up -d --build
```

Ngrok dashboard: http://localhost:4040  
Публичный URL появится в логах контейнера ngrok.

### 5. Проверить работоспособность

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

OpenAPI-документация: http://localhost:8000/docs

## API Endpoints

### Аутентификация

Все эндпоинты кроме `/auth/register` требуют аутентификацию:
- API-эндпоинты — заголовок `X-API-Key`
- `/webhooks/payment` — HMAC-SHA256 подпись в заголовке `X-Webhook-Signature`
- `/webhooks/stripe` — подпись Stripe в заголовке `Stripe-Signature`
- `/webhooks/fal/*` — внутренний callback от Fal.ai

#### Регистрация
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"external_user_id": "user-001"}'
```
Ответ: `{"api_key": "...", "message": "..."}`

### Баланс

```bash
# Получить баланс
curl http://localhost:8000/balance -H "X-API-Key: YOUR_KEY"

# История транзакций
curl http://localhost:8000/balance/transactions -H "X-API-Key: YOUR_KEY"
```

### Пополнение баланса

#### Через пользовательский webhook (HMAC-защищённый)

Каждый запрос должен содержать HMAC-SHA256 подпись тела в заголовке `X-Webhook-Signature`.
Ключ подписи задаётся в `PAYMENT_WEBHOOK_SECRET`.

```bash
# Пример генерации подписи и отправки:
BODY='{"external_user_id": "user-001", "amount": 100}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$PAYMENT_WEBHOOK_SECRET" | awk '{print $2}')
curl -X POST http://localhost:8000/webhooks/payment \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: $SIG" \
  -d "$BODY"
```

#### Через Stripe

Stripe отправляет webhook на `POST /webhooks/stripe`. Поддерживаемые события:
- `checkout.session.completed` — оплата через Stripe Checkout
- `payment_intent.succeeded` — успешный PaymentIntent

Для привязки платежа к пользователю передайте `external_user_id` в `metadata` при создании Checkout Session или PaymentIntent:

```python
stripe.checkout.Session.create(
    # ...
    metadata={"external_user_id": "user-001"},
)
```

Конвертация: `$1.00 = STRIPE_TOKENS_PER_DOLLAR` токенов (по умолчанию 100).

### Генерация

```bash
# Text-to-Image
curl -X POST http://localhost:8000/generations/text-to-image \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "A sunset over mountains", "image_size": "landscape_16_9"}'

# Image-to-Image
curl -X POST http://localhost:8000/generations/image-to-image \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Make it a painting", "image_urls": ["https://..."]}'

# Text-to-Video
curl -X POST http://localhost:8000/generations/text-to-video \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "A dragon flying", "resolution": "1080p", "duration": "5"}'

# Image-to-Video
curl -X POST http://localhost:8000/generations/image-to-video \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Animate the character", "image_url": "https://..."}'
```

Ответ (HTTP 202):
```json
{
  "task_id": "uuid",
  "status": "created",
  "type": "text_to_image",
  "cost": "10.00"
}
```

### Статус и результат

```bash
# Статус задачи
curl http://localhost:8000/generations/{task_id} -H "X-API-Key: YOUR_KEY"

# Список генераций
curl "http://localhost:8000/generations?offset=0&limit=20" -H "X-API-Key: YOUR_KEY"

# Скачать результат
curl -O http://localhost:8000/generations/{task_id}/download -H "X-API-Key: YOUR_KEY"
```

## Стоимость генерации (по умолчанию)

| Тип | Стоимость (токены) |
|---|---|
| text_to_image | 10 |
| image_to_image | 10 |
| text_to_video | 50 |
| image_to_video | 50 |

Цены конфигурируются в таблице `generation_prices` в базе данных.

## Разработка

### Установка зависимостей

```bash
python -m venv .venv
.venv/Scripts/activate  # Windows
source .venv/bin/activate  # Linux/Mac
pip install -r requirements-dev.txt
```

### Тесты

```bash
pytest tests/ -v
```

### Линтинг и форматирование (Ruff)

```bash
# Проверка
ruff check .

# Автоматическое исправление
ruff check --fix .

# Форматирование
ruff format .
```

### Нагрузочное тестирование (Locust)

Проверка SLA: время ответа API <= 5 секунд (95-й перцентиль).

```bash
pip install locust

# Интерактивный режим (веб-интерфейс на http://localhost:8089):
locust -f loadtests/locustfile.py --host http://localhost:8000

# Headless (для CI):
locust -f loadtests/locustfile.py --host http://localhost:8000 \
    --headless -u 50 -r 10 --run-time 60s \
    --csv loadtests/results
```

Переменные окружения для нагрузочного тестирования:
- `LOADTEST_API_KEY` — API-ключ предварительно зарегистрированного пользователя с балансом
- `LOADTEST_WEBHOOK_SECRET` — значение `PAYMENT_WEBHOOK_SECRET` для автоматического пополнения

При завершении Locust автоматически проверяет SLA и возвращает exit code 1 при нарушении.

## Архитектура

```
src/
├── main.py                  # FastAPI app entry point
├── core/                    # Config, logging, security
├── api/                     # Presentation Layer (routers, schemas, middleware)
├── domain/                  # Domain Layer (entities, interfaces)
├── services/                # Application Layer (use cases)
│   ├── stripe_service.py    # Stripe webhook processing
│   └── ...
├── infrastructure/          # Infrastructure Layer (DB, providers, Redis)
└── workers/                 # Celery tasks
```

Принципы:
- **Clean Architecture** с чётким разделением на слои
- **Repository Pattern** для работы с БД
- **Strategy Pattern** для провайдеров генерации (абстракция + fallback)
- **Circuit Breaker** для отказоустойчивости внешних сервисов
- Полностью **асинхронный** API и обработка задач

## Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `DB_NAME` | Имя базы данных | `ai_generator` |
| `DB_USER` | Пользователь PostgreSQL | `postgres` |
| `DB_PASSWORD` | Пароль PostgreSQL | `postgres` |
| `DB_HOST` | Хост PostgreSQL | `postgres` |
| `DB_PORT` | Порт PostgreSQL | `5432` |
| `REDIS_HOST` | Хост Redis | `redis` |
| `REDIS_PORT` | Порт Redis | `6379` |
| `REDIS_PASS` | Пароль Redis (пусто если без auth) | `` |
| `FAL_KEY` | API-ключ Fal.ai (основной провайдер) | — |
| `FAL_KEY_FALLBACK` | API-ключ Fal.ai (fallback-провайдер) | = FAL_KEY |
| `FAL_WEBHOOK_BASE_URL` | Публичный URL сервиса | `http://localhost:8000` |
| `PAYMENT_WEBHOOK_SECRET` | HMAC-SHA256 ключ для `/webhooks/payment` | — |
| `STRIPE_SECRET_KEY` | Секретный ключ Stripe | — |
| `STRIPE_WEBHOOK_SECRET` | Signing secret для Stripe webhook | — |
| `STRIPE_TOKENS_PER_DOLLAR` | Токенов за $1.00 | `100` |
| `RATE_LIMIT_MAX_REQUESTS` | Макс. запросов в окне | `10` |
| `RATE_LIMIT_WINDOW_SECONDS` | Окно rate limit (сек) | `60` |
| `RATE_LIMIT_BLOCK_SECONDS` | Блокировка при превышении (сек) | `60` |
| `WEBHOOK_MAX_RETRIES` | Макс. попыток доставки webhook | `5` |
| `WEBHOOK_RETRY_INTERVAL_SECONDS` | Интервал между попытками (сек) | `15` |
| `LOG_LEVEL` | Уровень логирования | `INFO` |
| `LOG_RETENTION_DAYS` | Хранение логов (дни) | `7` |
| `NGROK_AUTHTOKEN` | Токен ngrok (для docker-compose.ngrok.yml) | — |
