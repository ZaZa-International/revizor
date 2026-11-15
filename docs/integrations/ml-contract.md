# Контракт интеграции backend ↔ ML-сервис (schema_version 1.0)

## 1. Обзор

Backend (MGTS Infrastructure Intelligence) и ML-сервис общаются только через
контракт версии **1.0**. Единственный источник истины — Pydantic-модели
`backend/app/schemas/ml.py`. Доменные модели backend не импортируют ML-фреймворки;
вся связность сосредоточена в интерфейсе `MLProvider`
(`backend/app/application/interfaces/ml_provider.py`) и двух реализациях:

- `MockMLProvider` (`app/infrastructure/ml/mock_provider.py`) — детерминированные
  синтетические детекции для демо и тестов;
- `HTTPMLProvider` (`app/infrastructure/ml/http_provider.py`) — клиент внешнего
  ML-сервиса по HTTP.

Провайдер выбирается настройкой `ML_PROVIDER` (`mock` | `http`) через
`build_ml_provider(settings)` (`app/infrastructure/ml/factory.py`).

Артефакты контракта:

| Артефакт | Назначение |
|---|---|
| `backend/app/schemas/ml.py` | Pydantic-модели — эталон контракта |
| `contracts/ml/*.schema.json` | JSON Schema (draft 2020-12), выведены из Pydantic-моделей |
| `contracts/ml/examples/*.json` | Эталонные примеры запросов/ответов |
| `backend/tests/contracts/test_ml_contract.py` | Контрактные тесты (схемы ↔ примеры ↔ модели) |
| `docs/integrations/ml-examples/` | curl-примеры обращения к ML-сервису |

Изображения **не передаются по HTTP**: запрос содержит ссылку `storage_key` в
общем объектном хранилище (S3-совместимом) и опциональный `checksum_sha256`.
ML-сервис самостоятельно читает кадр из хранилища по ключу.

## 2. Endpoints

Базовый URL задаётся настройкой `ML_HTTP_BASE_URL` (по умолчанию
`http://localhost:8001`). Все тела — JSON, `Content-Type: application/json`.

| Метод | Путь | Тело запроса | Ответ (HTTP 200) | JSON Schema |
|---|---|---|---|---|
| GET | `/v1/health` | — | `MLHealth` | `health.schema.json` |
| GET | `/v1/model-info` | — | `MLModelInfo` | `model-info.schema.json` |
| POST | `/v1/infer` | `MLInferenceRequest` | `MLInferenceResponse` | `inference-request.schema.json` / `inference-response.schema.json` |
| POST | `/v1/infer/batch` | `{"schema_version": "1.0", "requests": [MLInferenceRequest, ...]}` | `MLBatchResponse` | `batch-request.schema.json` / `batch-response.schema.json` |

Ошибки (4xx/5xx) возвращаются в конверте `error-response.schema.json`:

```json
{"error": {"code": "inference_failed", "message": "...", "details": [], "request_id": "..."}}
```

Поля `details` и `request_id` опциональны; `code` и `message` обязательны.

## 3. Системы координат

- **bbox — абсолютные пиксели исходного изображения**, начало координат —
  левый верхний угол, X вправо, Y вниз. Значения — числа (допускаются дробные).
  Ограничения: `0 <= x_min < x_max <= width`, `0 <= y_min < y_max <= height`,
  где `width`/`height` — размеры изображения из запроса. Backend дополнительно
  проверяет, что каждый bbox ответа помещается в размеры изображения запроса;
  нарушение → `MLContractError`.
- **Геокоординаты — всегда (longitude, latitude), WGS84 / SRID 4326.**
  `longitude ∈ [-180, 180]`, `latitude ∈ [-90, 90]`. Пара передаётся только
  совместно: если задана одна координата, обязательна и вторая (иначе ошибка
  валидации). `heading_deg ∈ [0, 360)` — курс, градусы; `speed_mps >= 0` — м/с.

## 4. Поля и диапазоны

### MLInferenceRequest

| Поле | Тип | Ограничения |
|---|---|---|
| `schema_version` | string | константа `"1.0"` |
| `request_id` | UUID (строка RFC 4122) | обязателен на проводе; идемпотентный ключ запроса |
| `image.storage_key` | string | 1..1024 символа, ключ в объектном хранилище |
| `image.width`, `image.height` | integer | 1..32768 |
| `image.checksum_sha256` | string \| null | 64 hex-символа в нижнем регистре |
| `metadata.observed_at` | datetime (ISO 8601) \| null | время съёмки кадра |
| `metadata.longitude` / `latitude` | float \| null | см. §3, только парой |
| `metadata.heading_deg` | float \| null | `[0, 360)` |
| `metadata.speed_mps` | float \| null | `>= 0` |
| `metadata.route_id`, `metadata.tracking_id` | string \| null | произвольные идентификаторы |
| `metadata.frame_index` | integer \| null | `>= 0` |

### MLDetection

| Поле | Тип | Ограничения |
|---|---|---|
| `detection_id` | UUID | уникален в пределах ответа (см. §8) |
| `object_type` | string | 1..64 символа; канонические коды — ниже |
| `condition_class` | string \| null | ≤ 64 символов; канонические коды — ниже |
| `confidence` | float | `[0, 1]` |
| `severity` | integer \| null | `1..5`; null, если состояние не оценивалось |
| `bbox` | MLBBox | см. §3 |
| `embedding` | float[] \| null | вектор признаков для дедупликации/поиска |
| `attributes` | object | произвольные дополнительные атрибуты |

Канонические `object_type` (реестр `app/domain/assets/taxonomy.py`):
`telecom_well`, `pole`, `telecom_cabinet`, `cable_line`, `other`.

Канонические `condition_class` (`app/domain/observations/condition.py`) и
severity по умолчанию:

| Код | Severity по умолчанию | Смысл |
|---|---|---|
| `ok` | null (дефекта нет) | исправен |
| `damaged` | 3 | повреждение |
| `damaged_cover` | 4 | повреждённая крышка колодца |
| `missing_cover` | 5 | отсутствующая крышка колодца |
| `door_open` | 3 | открытая дверца шкафа |
| `tilted` | 4 | наклон опоры |
| `subsided` | 4 | просадка колодца |
| `cable_sag` | 3 | провисание кабеля |
| `cable_break` | 5 | обрыв кабеля |
| `unknown` | null (не определено) | состояние не распознано |

ML-сервису рекомендуется возвращать канонические коды. Backend нормализует
алиасы (`broken` → `damaged`, `no_cover` → `missing_cover` и т.п.) и неизвестные
значения приводит к `unknown`. Для `ok` и `unknown` mock-провайдер возвращает
`severity = null`; реальный сервис может делать так же.

### MLInferenceResponse / MLBatchResponse / MLHealth / MLModelInfo

- `MLInferenceResponse`: `schema_version` (`"1.0"`), `request_id` (обязан
  совпадать с запросом), `model` (`MLModelInfo`), `detections` (список, может
  быть пустым), `inference_time_ms` (float `>= 0` | null).
- `MLBatchResponse`: `schema_version`, `model`, `results` — список
  `MLBatchItemResult` (см. §7).
- `MLHealth`: `status` ∈ `ok | degraded | unavailable`, `model_loaded` (bool),
  `provider` (string), `details` (object).
- `MLModelInfo`: `name`, `version`, `schema_version` (текущее значение `"1.0"`).

Лишние поля запрещены везде (`additionalProperties: false` / `extra="forbid"`).

## 5. Пустой результат — валидный результат

`detections: []` при HTTP 200 — **штатный исход** («на кадре нет объектов
инфраструктуры»), а не ошибка. ML-сервис не должен возвращать 4xx/5xx или
`error`-конверт, если модель просто ничего не нашла. Backend корректно
обрабатывает пустой список (кадр считается обработанным без детекций).
Пример: `contracts/ml/examples/response-empty.json`.

## 6. Семантика ошибок

### Коды ошибок ML-сервиса (конверт `{"error": {...}}`)

| `error.code` | Рекомендуемый HTTP | Смысл |
|---|---|---|
| `inference_failed` | 422 (или 400) | модель не смогла обработать кадр (битый JPEG, OOM инференса и т.п.) |
| `invalid_request` | 400 | запрос не соответствует контракту |
| `model_not_loaded` | 503 | модель не загружена/прогревается |
| `internal_error` | 500 | внутренняя ошибка сервиса |

Список открытый: новые коды добавляются без изменения schema_version.

### Как backend отображает сбои в исключения (`app/core/exceptions.py`)

| Ситуация | Исключение | HTTP backend | `code` | Повтор? |
|---|---|---|---|---|
| Таймаут запроса, исчерпаны попытки | `MLTimeoutError` | 504 | `ml_timeout` | да (до исчерпания) |
| ConnectError / 5xx, исчерпаны попытки | `MLUnavailableError` | 503 | `ml_unavailable` | да (до исчерпания) |
| Невалидный JSON, нарушение Pydantic-схемы, `schema_version != "1.0"`, чужой `request_id`, bbox вне изображения, 4xx | `MLContractError` | 502 | `ml_contract_violation` | нет |
| 4xx с `error.code == "inference_failed"` | `MLInferenceError` | 502 | `ml_inference_failed` | нет |

Правило для 4xx простое: **любой 4xx → `MLContractError`, кроме тела с
`error.code == "inference_failed"` → `MLInferenceError`**. 4xx никогда не
повторяются. 5xx повторяются согласно §10; после исчерпания попыток —
`MLUnavailableError` (даже если тело содержит `inference_failed`).

Все ошибки фиксируются метрикой `ml_errors_total{provider, code}`; длительность
операций — `ml_inference_duration_seconds{provider, operation}`.

## 7. Частичные ошибки в batch

`POST /v1/infer/batch` обрабатывает каждый кадр независимо. Ответ —
`MLBatchResponse.results`, по одному `MLBatchItemResult` на запрос:

- `status: "OK"` — обязан содержать `response` (полный `MLInferenceResponse`,
  `request_id` внутри ответа совпадает с `request_id` элемента);
- `status: "ERROR"` — обязан содержать `error` (`{code, message}`); ошибка
  одного кадра **не прерывает** обработку остальных и не поднимается как
  исключение на уровне всего batch.

Рекомендуется сохранять порядок запросов; сопоставление выполняется по
`request_id`. Backend проверяет, что каждый `request_id` результата принадлежит
исходному списку запросов, и валидирует bbox каждого OK-ответа. Транспортный
сбой (таймаут, 5xx, обрыв соединения) относится ко всему batch и поднимается
как исключение (§6). Пример частичного ответа:
`contracts/ml/examples/batch-response-partial.json`.

## 8. Уникальность detection_id

`detection_id` — UUID v4, **уникальный в пределах одного ответа**. Повторы
отклоняются Pydantic-валидатором `MLInferenceResponse` (→ `MLContractError` у
HTTP-провайдера). Идентификатор должен быть стабильным при повторной обработке
того же `request_id` (идемпотентность): это позволяет backend дедуплицировать
детекции при ретраях. JSON Schema draft 2020-12 не умеет выражать уникальность
ключа по элементам массива — правило обеспечивается Pydantic-моделью; в схеме
дополнительно стоит `uniqueItems: true` (отклоняет полностью идентичные элементы).

## 9. schema_version vs версия модели

- `schema_version` — версия **контракта обмена**. В запросах/ответах это
  `Literal["1.0"]`: любое другое значение отклоняется обеими сторонами.
- `model.version` — версия **весов/сборки модели** (произвольная строка,
  например `1.2.0` или `2026-07-17`). Может меняться без изменения контракта.
- `model.name` — человекочитаемое имя модели.

Не путать: обновление модели не требует нового schema_version, пока формат
запросов/ответов не изменился.

## 10. Повторы и таймауты (HTTPMLProvider)

Настройки (`app/config.py`, переменные окружения):

| Настройка | По умолчанию | Смысл |
|---|---|---|
| `ML_HTTP_TIMEOUT_SECONDS` | 30.0 | таймаут одного HTTP-запроса |
| `ML_HTTP_RETRIES` | 2 | число повторов сверх первой попытки |
| `ML_HTTP_BACKOFF_SECONDS` | 0.5 | база экспоненциальной задержки |

Политика: всего `1 + ML_HTTP_RETRIES` попыток. Повторяются **таймауты
(`httpx.TimeoutException`), ошибки соединения (`httpx.ConnectError`) и HTTP
5xx**. Задержка перед повтором `N` (0-индексация):
`ML_HTTP_BACKOFF_SECONDS * 2**N + jitter`, jitter равномерно из `[0, 0.1]` с.
**4xx не повторяются никогда.** После исчерпания попыток: таймаут →
`MLTimeoutError`, соединение/5xx → `MLUnavailableError`.

ML-сервису рекомендуется быть идемпотентным по `request_id`: повторный запрос
с тем же `request_id` должен возвращать тот же результат (или безопасно
переобрабатывать кадр).

## 11. Версионирование и совместимость

- **Аддитивные изменения** (новые опциональные поля, новые коды ошибок, новые
  значения справочников) — минорные: schema_version остаётся `"1.0"`, префикс
  `/v1` не меняется. Старые клиенты игнорируют новые поля; новые поля не должны
  быть обязательными.
- **Ломающие изменения** (удаление/переименование полей, сужение диапазонов,
  смена семантики координат) — только через новый `schema_version` (например,
  `"2.0"`) **и новый префикс эндпоинтов** (`/v2/...`). Backend фиксирует
  поддерживаемую версию в `Literal`-полях и настройке `ML_CONTRACT_VERSION`;
  переключение выполняется осознанно, с миграцией обеих сторон.
- JSON Schema-файлы в `contracts/ml/` регенерируются/правятся синхронно с
  `app/schemas/ml.py`; контрактные тесты
  (`pytest -m contract`, `backend/tests/contracts/test_ml_contract.py`)
  проверяют согласованность схем, примеров и моделей.

Ограничения JSON Schema (осознанные решения): схема не выражает (а) порядок
`min < max` внутри bbox и (б) уникальность `detection_id` по элементам массива;
оба правила обеспечиваются Pydantic-моделями и проверяются контрактными
тестами. На проводе обязательны поля, которые в Pydantic имеют значения по
умолчанию (`schema_version`, `request_id`, `detections` и т.д.): JSON Schema
намеренно строже, чтобы обмен был явным.

## 12. Как ML-команде подключить реальную модель

1. Реализовать HTTP-сервис с четырьмя эндпоинтами из §2 (например, FastAPI +
   PyTorch/TensorRT — стек на стороне ML не ограничивается).
2. Принимать `MLInferenceRequest`, читать кадр из объектного хранилища по
   `image.storage_key` (доступ к хранилищу настраивается на стороне ML),
   возвращать `MLInferenceResponse` строго по контракту: канонические коды
   (§4), bbox в абсолютных пикселях (§3), уникальные `detection_id` (§8),
   пустой список вместо ошибки (§5).
3. Отдавать `GET /v1/health` и `GET /v1/model-info` для мониторинга; ошибки —
   в конверте §6.
4. Проверить сервис контрактными тестами и примерами:
   `cd backend && uv run pytest tests/contracts/test_ml_contract.py -m contract`;
   смоук-запросы — `docs/integrations/ml-examples/`.
5. Переключить backend: `ML_PROVIDER=http`, `ML_HTTP_BASE_URL=http://<ml-host>:<port>`.

**Изменения в доменном коде backend не требуются**: вся интеграция изолирована
в `MLProvider`/`HTTPMLProvider`. Новые типы объектов и дефектов добавляются в
реестры домена (`app/domain/assets/taxonomy.py`,
`app/domain/defects/taxonomy.py`) отдельно от ML-контракта.

## 13. Mock-провайдер (дисклеймер)

`MockMLProvider` (`ML_PROVIDER=mock`, значение по умолчанию) генерирует
**синтетические** детекции: 0..3 объекта на кадр, ~15% запросов дают пустой
результат. Результат детерминирован по `request_id` (один и тот же запрос всегда
даёт одинаковые `detection_id` и поля). Используются канонические коды типов и
состояний, `confidence ∈ [0.55, 0.97]`, severity по умолчанию для состояния
(null для `ok`/`unknown`), bbox строго внутри изображения, `embedding = null`,
`attributes = {"mock": true}`. Имитируется задержка ~5 мс.

**Это не инференс**: качество, координаты и состояния объектов не имеют
отношения к реальному содержимому кадра. Только для демо, разработки и тестов.
`model_info`: `mock-infrastructure-detector` / `0.1.0-mock`.

## 14. Безопасность

- ML-сервис размещается **в приватной сети** (docker-compose network / VPC /
  кластерная сеть) и **не публикуется наружу**: ни публичного IP, ни проброса
  портов на интернет. Backend обращается к нему по внутреннему адресу.
- Аутентификация между backend и ML в v1.0 отсутствует (доверенная приватная
  сеть). Опциональный API-ключ (заголовок `X-API-Key` или Bearer) может быть
  добавлен аддитивно в минорной версии контракта; до этого не передавать
  секреты в запросах.
- По HTTP передаются только ссылки на кадры (`storage_key`) и метаданные —
  **никаких байтов изображений**. Доступ ML-сервиса к хранилищу — по отдельным
  credentials с минимальными правами (чтение префикса загрузок).
- Логи backend не содержат содержимого изображений и секретов; логируются
  только идентификаторы (`request_id`), коды ошибок и метрики.
