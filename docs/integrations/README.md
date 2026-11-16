# Integration Contracts — точка входа

Каталог контрактов MGTS Infrastructure Intelligence для интегрирующихся команд.
Здесь собрано всё, что нужно frontend- и ML-командам: схемы, примеры,
инструменты проверки и правила изменения контрактов.

## Для frontend-команды

### Источник истины

- **OpenAPI 3.1**: [`contracts/openapi/openapi.json`](../../contracts/openapi/openapi.json)
  (генерируется из живого приложения: `make openapi`). Интерактивно:
  Swagger UI `/docs`, ReDoc `/redoc` на запущенном API.
- **Справочник разработчика (русский)**: [`docs/api/`](../api/overview.md) —
  [overview](../api/overview.md), [authentication](../api/authentication.md),
  [errors](../api/errors.md),
  [pagination-filtering](../api/pagination-filtering.md),
  [geospatial](../api/geospatial.md),
  [upload-and-processing](../api/upload-and-processing.md),
  [workflows](../api/workflows.md) (сквозные curl-сценарии).
- **Краткий контракт**: [frontend-contract.md](frontend-contract.md).
- **Эталонные примеры ответов**: [`contracts/examples/api/`](../../contracts/examples/api/)
  (18 файлов: login, uploads, jobs, frames, assets, observations, defects,
  reviews, map, routes, analytics, ошибки). Валидируются контрактными тестами
  против компонентных схем OpenAPI — можно использовать как моки.

### TypeScript-клиент

```bash
make ts-client        # → contracts/typescript/schema.d.ts (openapi-typescript)
```

Типы + runtime-клиент [openapi-fetch](https://openapi-ts.dev/openapi-fetch/):
`createClient<paths>({ baseUrl })` с заголовком `Authorization: Bearer …`;
типизированные `client.GET("/api/v1/assets", { params: { query: … } })`.
Полный пример — [contracts/typescript/README.md](../../contracts/typescript/README.md).

### Проверки контракта (CI и локально)

| Команда | Что проверяет |
|---|---|
| `make openapi-check` | committed `openapi.json` == live `app.openapi()` (drift; exit 1 + unified diff) |
| `make breaking-check` | breaking-изменения относительно `origin/main` (tufin/oasdiff в docker; exit 1 при breaking, exit 2 если docker недоступен) |
| `cd backend && uv run pytest tests/contracts -m contract` | контрактные тесты: ML-схемы/примеры/модели, frontend-сценарии, OpenAPI-структура и примеры API |

### Правила изменения контракта (frontend)

1. Любое изменение API-поведения → обновление OpenAPI (`make openapi`),
   примеров `contracts/examples/api/`, документации `docs/api/` и
   `frontend-contract.md`, контрактных тестов.
2. Ломающее изменение (pre-1.0 допускается) → запись в
   [CHANGELOG](../../CHANGELOG.md) + `make breaking-check` для ревью +
   уведомление frontend-команды. После 1.0 — только `/api/v2`.
3. Аддитивные поля — минорные: клиент игнорирует незнакомые поля.
4. Не редактируйте `schema.d.ts` и `openapi.json` вручную — только генерация.

## Для ML-команды

### Источник истины

- **Контракт v1.0**: [ml-contract.md](ml-contract.md) — 4 endpoint'а
  (`GET /v1/health`, `GET /v1/model-info`, `POST /v1/infer`,
  `POST /v1/infer/batch`), системы координат (bbox — абсолютные пиксели;
  гео — lon/lat WGS84), семантика ошибок, повторы/таймауты, идемпотентность
  по `request_id`, пустой detections — валидный результат.
- **Pydantic-модели (эталон)**: `backend/app/schemas/ml.py`.
- **JSON Schema (draft 2020-12)**: [`contracts/ml/`](../../contracts/ml/) —
  `inference-request/response`, `batch-request/response`, `health`,
  `model-info`, `error-response`.
- **Эталонные примеры**: [`contracts/ml/examples/`](../../contracts/ml/examples/);
  curl-смоуки: [ml-examples/](ml-examples/).

### Провайдеры и конфигурация

| `ML_PROVIDER` | Реализация | Назначение |
|---|---|---|
| `mock` (default) | `MockMLProvider` | Детерминированные синтетические детекции для демо/тестов (не инференс!) |
| `http` | `HTTPMLProvider` | Внешний ML-сервис: `ML_HTTP_BASE_URL` (default `http://localhost:8001`), таймаут 30 с, 1+2 попытки, backoff 0.5 с |

Переключение на реальную модель: `ML_PROVIDER=http`,
`ML_HTTP_BASE_URL=http://<ml-host>:<port>` — изменения доменного кода backend
не требуются. ML-сервис размещается в приватной сети и читает кадры из
общего S3-хранилища по `storage_key` ([storage.md](storage.md)).

### Проверка ML-сервиса

```bash
cd backend && uv run pytest tests/contracts/test_ml_contract.py -m contract
```

Тесты проверяют согласованность JSON Schema ↔ примеры ↔ Pydantic-модели,
включая правила, не выразимые в JSON Schema (bbox min < max, уникальность
`detection_id`). Смоук-запросы к живому сервису — `docs/integrations/ml-examples/`.

### Правила изменения контракта (ML)

- Аддитивные изменения (новые опциональные поля, коды ошибок, значения
  справочников) — `schema_version` остаётся `"1.0"`.
- Ломающие — только новый `schema_version` **и** новый префикс `/v2`;
  синхронно: `app/schemas/ml.py`, `contracts/ml/*.schema.json`, примеры,
  контрактные тесты, `ml-contract.md`, CHANGELOG.
- Обновление весов модели (`model.version`) не требует смены `schema_version`.

## Версионирование (общее)

- API: `/api/v1`, проект pre-1.0 — breaking допускаются с CHANGELOG + docs +
  тестами; post-1.0 — `/api/v2`.
- ML-контракт: независимый `schema_version` (сейчас `"1.0"`).
- OpenAPI-контракт коммитится; drift ловится `make openapi-check`,
  breaking — `make breaking-check`.

## Процесс изменения контрактов (для всех команд)

1. Обсудите изменение с lead backend'а (затронутые команды — в курсе).
2. Реализуйте изменение + синхронно обновите: схемы/модели, примеры,
   документацию (`docs/api/`, `docs/integrations/`), CHANGELOG.
3. Прогоните: `make openapi && make openapi-check && make breaking-check`,
   `cd backend && uv run pytest tests/contracts -m contract`.
4. Ломающее изменение явно помечается в CHANGELOG и PR; frontend/ML
   подтверждают совместимость до merge.
5. После merge лид перегенерирует `openapi.json` и `schema.d.ts`
   (`make openapi && make ts-client`).

Контакт: lead backend-команды (через PR/review в репозитории). История
решений — [docs/decisions/](../decisions/), аудит и план исправлений —
[docs/audit/backend-audit.md](../audit/backend-audit.md).
