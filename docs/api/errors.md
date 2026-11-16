# Ошибки API

Все ошибки (4xx/5xx), включая ошибки валидации FastAPI, возвращаются в
**едином конверте**:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [
      {
        "field": "query.page_size",
        "message": "Input should be less than or equal to 100",
        "type": "less_than_equal"
      }
    ],
    "request_id": "b2c3d4e5-2222-4333-9444-555566667777"
  }
}
```

| Поле | Тип | Описание |
|---|---|---|
| `error.code` | string | Машиночитаемый код (каталог ниже). Открытый список: новые коды добавляются аддитивно |
| `error.message` | string | Человекочитаемое сообщение (английский). Не парсите его — используйте `code` |
| `error.details` | array | Детали валидации: `{field, message, type}`; для прочих ошибок — `[]` |
| `error.request_id` | string \| null | Корреляция с заголовком `x-request-id` ответа и логами сервера |

`field` — точечный путь: `body.longitude`, `query.page_size`, `path.asset_id`.
Значения пользовательского ввода в `details` не включаются (защита от утечек).

Готовые примеры: [error-not-found.json](../../contracts/examples/api/error-not-found.json),
[error-validation.json](../../contracts/examples/api/error-validation.json),
[error-conflict.json](../../contracts/examples/api/error-conflict.json),
[error-rate-limited.json](../../contracts/examples/api/error-rate-limited.json).

## Каталог кодов

| Код | HTTP | Когда возникает | Повтор запроса |
|---|---|---|---|
| `validation_error` | 422 | Невалидные параметры/тело (FastAPI), bbox, даты, metadata JSON, неизвестный `sort_by`, `Idempotency-Key` > 128 | Нет — исправьте запрос по `details` |
| `authentication_failed` | 401 | Нет/невалидный/просроченный/отозванный токен, неверный логин/пароль, неактивный пользователь | После повторного login |
| `permission_denied` | 403 | Недостаточная роль (VIEWER на мутации/медиа), удаление чужой загрузки | Нет |
| `not_found` | 404 | Сущность не найдена (`Asset '<id>' not found`) | Нет |
| `storage_object_not_found` | 404 | Ключ отсутствует в объектном хранилище (`GET /files/...`) | Нет |
| `conflict` | 409 | Конфликт данных: версия актива (optimistic locking), активный job загрузки, удаление загрузки с jobs, unique/FK | Да — после перезагрузки сущности (см. ниже) |
| `invalid_job_state` | 409 | retry/cancel в недопустимом статусе job | Нет — сначала прочитайте статус job |
| `idempotency_conflict` | 409 | Тот же `Idempotency-Key` использован с другим payload | Нет — новый ключ для нового запроса |
| `rate_limited` | 429 | Превышен лимит login/upload | Да — через `Retry-After` секунд |
| `payload_too_large` | 413 | Тело больше лимита (multipart 2 GiB + 1 MB overhead; JSON 2 MiB). Отказ **до аутентификации**, без буферизации | Нет — уменьшите файл/тело |
| `ml_contract_violation` | 502 | ML-сервис нарушил контракт (схема, `schema_version`, чужой `request_id`, bbox вне кадра, 4xx) | Нет — эскалация ML-команде |
| `ml_inference_failed` | 502 | ML вернул `error.code = inference_failed` (битый кадр и т.п.) | Нет (кадр помечается FAILED; retry job обработает остальные) |
| `ml_provider_error` | 502 | Прочие ошибки ML-провайдера | Осторожно |
| `ml_unavailable` | 503 | ML недоступен (connect/5xx, попытки исчерпаны) | Да — с backoff |
| `storage_unavailable` | 503 | Объектное хранилище недоступно | Да — с backoff |
| `ml_timeout` | 504 | Таймаут ML-запроса, попытки исчерпаны | Да — с backoff |
| `internal_error` | 500 | Непредвиденная ошибка (детали только в логах по `request_id`) | Да — однократно, затем эскалация |
| `http_error` | прочие | Стандартные HTTP-ошибки вне каталога (например, 405) | По ситуации |

## Рекомендации по повторам (retry)

### 429 — rate limit
Ответ содержит заголовок **`Retry-After: <секунды>`**. Ждите указанное время
(окно лимита — минута), повторяйте с экспоненциальным backoff и jitter.
Не retry'те немедленно в цикле.

### 409 — конфликт версий актива (optimistic locking)
`PATCH /api/v1/assets/{id}` с устаревшим `expected_version` →
`{"code": "conflict", "message": "Asset version mismatch; reload and retry"}`.
Алгоритм: **GET актуальной карточки → перечитать `version` → повторить PATCH**
с новым `expected_version` (и пересмотреть изменения — их мог внести другой
оператор). Без `expected_version` блокировка не применяется (last-write-wins).

### 409 — idempotency_conflict
`Idempotency-Key` уже использован с **другим** payload (fingerprint запроса).
Повтор с идентичным payload вернёт сохранённый ответ (200/201), а не конфликт.
Для нового запроса сгенерируйте новый ключ. Ключ scoped по пользователю и
endpoint'у; длина ≤ 128 символов.

### 409 — invalid_job_state
Прочитайте `GET /jobs/{id}`: retry допустим для FAILED / PARTIALLY_COMPLETED /
CANCELLED (и «зависшего» PROCESSING), cancel — для PENDING / QUEUED /
PROCESSING. См. [upload-and-processing.md](upload-and-processing.md).

### 502 / 503 / 504 — ML и хранилище
`ml_unavailable` (503), `storage_unavailable` (503), `ml_timeout` (504) —
**повторяемые** сбои инфраструктуры: retry с экспоненциальным backoff
(например, 1 с → 2 с → 4 с, максимум 3–5 попыток). Покадровые сбои ML не
валят job: кадр получает FAILED, job — PARTIALLY_COMPLETED; повторная
обработка идемпотентна (`POST /jobs/{id}/retry`).
`ml_contract_violation` и `ml_inference_failed` (502) **не повторяйте** —
это ошибка контракта/данных, нужен разбор с ML-командой по `request_id`.

## Корреляция: request_id

- Каждый ответ содержит заголовок `x-request-id`; то же значение — в
  `error.request_id` и во всех логах/метриках запроса.
- Можно передать свой `x-request-id` в запросе (обрезается до 64 символов) —
  сервер пробросит его сквозь pipeline и логи.
- При обращении в поддержку указывайте `request_id`, время и endpoint.

## Обработка на клиенте (рекомендация)

```typescript
if (!response.ok) {
  const { error } = await response.json();
  switch (error.code) {
    case "authentication_failed": return relogin();
    case "rate_limited": return retryAfter(response.headers.get("Retry-After"));
    case "conflict": return reloadAndRetry();
    default: report(error.code, error.request_id);
  }
}
```

См. также: [authentication.md](authentication.md),
[pagination-filtering.md](pagination-filtering.md), [workflows.md](workflows.md).
