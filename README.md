# AI Generation Microservice

Микросервис для генерации изображений и видео с использованием Fal.ai API (модель WAN 2.5).

## Возможности

- **4 типа генерации**: text-to-image, image-to-image, text-to-video, image-to-video
- **Система пользователей** с балансом в условных токенах
- **Интеграция со Stripe** — пополнение баланса через Stripe Checkout
- **Асинхронная обработка** генераций через Celery + Redis
- **Жизненный цикл задач**: `created -> queued -> processing -> completed / failed`
- **Автоматический возврат токенов** при ошибках генерации
- **Мониторинг зависших задач** — Celery Beat проверяет каждые 2 минуты
- **Доставка webhook-уведомлений** клиенту (5 попыток, интервал 15 сек)
- **Rate limiting**: 10 запросов/мин, блокировка на 60 сек при превышении
- **Метрики Prometheus**: количество генераций, ошибки, себестоимость, API-запросы
- **Логирование** в JSON-формате с ротацией 7 дней
- **Circuit breaker** + fallback-провайдер для отказоустойчивости
- **Веб-интерфейс** — регистрация, просмотр баланса, генерация, история
- **Админ-панель** на `/admin` (sqladmin)
- **Ngrok-туннель** для разработки

## Технологии

- Python 3.11, FastAPI, Uvicorn
- PostgreSQL 15, SQLAlchemy 2.0 (async), Alembic
- Celery 5 + Celery Beat, Redis 7
- Stripe (webhook-интеграция), fal-client (Fal.ai SDK)
- Prometheus, Ruff, Pylint, Locust
- Docker, Docker Compose

## Быстрый старт

### 1. Клонировать и настроить

Отредактируйте `.env`:
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` — PostgreSQL
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASS` — Redis
- `FAL_KEY` — API-ключ Fal.ai
- `FAL_WEBHOOK_BASE_URL` — публичный URL сервиса (ngrok)
- `SECRET_KEY` — секрет для подписи токенов Fal webhook и админ-панели
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` — ключи Stripe
- `PAYMENT_WEBHOOK_SECRET` — HMAC-ключ для `/webhooks/payment`

### 2. Запуск

```bash
docker compose up -d --build
```

### 3. Запуск с ngrok

```bash
docker compose -f docker-compose.yml -f docker-compose.ngrok.yml up -d --build
```

Ngrok dashboard: http://localhost:4040

### Сервисы

| Сервис | Порт | Описание |
|---|---|---|
| app | 8000 | FastAPI API + веб-интерфейс |
| celery-worker | — | Фоновая обработка генераций |
| celery-beat | — | Периодические задачи (мониторинг зависших) |
| postgres | 5432 | PostgreSQL |
| redis | 6379 | Redis |
| prometheus | 9090 | Метрики |

### 4. Проверка

```bash
curl http://localhost:8000/health
```

- Веб-интерфейс: http://localhost:8000
- OpenAPI: http://localhost:8000/docs
- Админ-панель: http://localhost:8000/admin (пароль = SECRET_KEY)

## API

### Аутентификация

Все эндпоинты кроме `/auth/register` требуют аутентификацию:
- API: заголовок `X-API-Key`
- `/webhooks/payment`: HMAC-SHA256 в `X-Webhook-Signature`
- `/webhooks/stripe`: Stripe Signature
- `/webhooks/fal/*`: HMAC-токен в query parameter

### Эндпоинты

| Метод | URL | Описание |
|---|---|---|
| POST | `/auth/register` | Регистрация, возвращает API-ключ |
| GET | `/balance` | Текущий баланс |
| POST | `/balance/checkout` | Создать Stripe Checkout Session |
| GET | `/balance/transactions` | История транзакций |
| POST | `/generations/text-to-image` | Генерация изображения из текста |
| POST | `/generations/image-to-image` | Редактирование изображения |
| POST | `/generations/text-to-video` | Генерация видео из текста |
| POST | `/generations/image-to-video` | Генерация видео из изображения |
| GET | `/generations` | Список генераций |
| GET | `/generations/{id}` | Статус генерации |
| GET | `/generations/{id}/download` | Скачать результат |
| POST | `/webhooks/payment` | Пополнение баланса (HMAC) |
| POST | `/webhooks/stripe` | Stripe webhook |
| POST | `/webhooks/fal/{id}` | Fal.ai callback |
| GET | `/health` | Healthcheck |
| GET | `/metrics` | Prometheus метрики |

## Разработка

```bash
python -m venv .venv
source .venv/bin/activate  # или .venv\Scripts\activate
pip install -r requirements-dev.txt

# Тесты
pytest tests/ -v

# Линтинг
ruff check .
pylint src/ tests/ loadtests/ --rcfile=.pylintrc

# Нагрузочное тестирование
DRY_RUN=true docker compose up -d app postgres redis
locust -f loadtests/locustfile.py --host http://localhost:8000
```

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
| `REDIS_PASS` | Пароль Redis | `` |
| `SECRET_KEY` | Секрет приложения (админка + подпись Fal webhook) | `change-me` |
| `FAL_KEY` | API-ключ Fal.ai | — |
| `FAL_KEY_FALLBACK` | API-ключ fallback-провайдера | = FAL_KEY |
| `FAL_WEBHOOK_BASE_URL` | Публичный URL сервиса | `http://localhost:8000` |
| `PAYMENT_WEBHOOK_SECRET` | HMAC-ключ для `/webhooks/payment` | — |
| `STRIPE_SECRET_KEY` | Секретный ключ Stripe | — |
| `STRIPE_WEBHOOK_SECRET` | Signing secret Stripe webhook | — |
| `STRIPE_TOKENS_PER_DOLLAR` | Токенов за $1.00 | `100` |
| `RATE_LIMIT_MAX_REQUESTS` | Макс. запросов в минуту | `10` |
| `RATE_LIMIT_BLOCK_SECONDS` | Блокировка при превышении (сек) | `60` |
| `NGROK_AUTHTOKEN` | Токен ngrok | — |
