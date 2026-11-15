# Добавление нового ML-провайдера

Backend изолирован от ML единственной точкой связности — протоколом
`MLProvider` (`backend/app/application/interfaces/ml_provider.py`). В backend
**нет ML-фреймворков** (torch/tensorflow и т.п.): инференс выполняется либо
внешним HTTP-сервисом, либо детерминированным mock. См.
[ADR-0004](../decisions/ADR-0004-ml-provider-isolation.md) и
[контракт интеграции v1.0](../integrations/ml-contract.md) (эталонный документ
по контракту; здесь — только провайдерная часть).

## Протокол MLProvider

```python
@runtime_checkable
class MLProvider(Protocol):
    name: str

    async def health(self) -> MLHealth: ...
    async def model_info(self) -> MLModelInfo: ...
    async def infer_image(self, request: MLInferenceRequest) -> MLInferenceResponse: ...
    async def infer_batch(self, requests: list[MLInferenceRequest]) -> MLBatchResponse: ...
    async def close(self) -> None: ...
```

Все модели — Pydantic из `app/schemas/ml.py` (`schema_version: Literal["1.0"]`,
`extra="forbid"`). Требования к реализации:

- `infer_image`: ответ обязан иметь тот же `request_id`, что и запрос; каждый
  bbox — в абсолютных пикселях внутри `width × height` запроса; `detection_id`
  уникальны в пределах ответа. Пустой `detections: []` — валидный результат.
- `infer_batch`: по одному `MLBatchItemResult` на запрос; ошибка одного кадра
  (`status="ERROR"`) не прерывает batch и не поднимается как исключение.
- Ошибки — только подклассы `MLProviderError` из `app/core/exceptions.py`:
  `MLTimeoutError`, `MLUnavailableError` (повторяемые), `MLContractError`,
  `MLInferenceError` (неповторяемые).
- Изображения по HTTP не передаются: запрос несёт `image.storage_key` в общем
  S3-хранилище; сервис читает кадр сам.
- Содержимое изображений и секреты не логируются; только `request_id`, коды
  ошибок, метрики (`ml_errors_total`, `ml_inference_duration_seconds`).

## Существующие реализации

| Провайдер | Файл | Назначение |
|---|---|---|
| `MockMLProvider` (`name="mock"`) | `app/infrastructure/ml/mock_provider.py` | Демо/тесты: синтетические детекции, детерминированные по `request_id`, 0..3 объекта, ~15% пустых ответов. **Не инференс** |
| `HTTPMLProvider` (`name="http"`) | `app/infrastructure/ml/http_provider.py` | Клиент внешнего ML-сервиса по контракту v1.0 |

Выбор — `build_ml_provider(settings)` (`app/infrastructure/ml/factory.py`) по
настройке `ML_PROVIDER` (`mock` | `http`).

### HTTPMLProvider: endpoints, повторы, ошибки

Эндпоинты (базовый URL — `ML_HTTP_BASE_URL`):

| Метод | Путь | Операция |
|---|---|---|
| GET | `/v1/health` | `health()` |
| GET | `/v1/model-info` | `model_info()` |
| POST | `/v1/infer` | `infer_image()` |
| POST | `/v1/infer/batch` | `infer_batch()` |

Политика повторов (`app/config.py`):

| Настройка | По умолчанию | Смысл |
|---|---|---|
| `ML_HTTP_TIMEOUT_SECONDS` | 30.0 | таймаут одного запроса |
| `ML_HTTP_RETRIES` | 2 | повторов сверх первой попытки (всего `1 + retries`) |
| `ML_HTTP_BACKOFF_SECONDS` | 0.5 | база задержки: `0.5 * 2**N + jitter[0, 0.1]` с |

Повторяются таймауты, `ConnectError` и HTTP 5xx. **4xx не повторяются никогда.**
После исчерпания попыток: таймаут → `MLTimeoutError`, соединение/5xx →
`MLUnavailableError`.

Маппинг ответов в исключения:

| Ситуация | Исключение | Повтор? |
|---|---|---|
| Невалидный JSON / нарушение Pydantic-схемы / `schema_version != "1.0"` / чужой `request_id` / bbox вне изображения | `MLContractError` | нет |
| Любой 4xx | `MLContractError` | нет |
| 4xx с телом `{"error": {"code": "inference_failed"}}` | `MLInferenceError` | нет |
| Таймаут (попытки исчерпаны) | `MLTimeoutError` | да, до исчерпания |
| ConnectError / 5xx (попытки исчерпаны) | `MLUnavailableError` | да, до исчерпания |

Подробности семантики ошибок и batch — в [ml-contract.md](../integrations/ml-contract.md) §6–§7.

## Как подключить внешний ML-сервис (без нового кода)

1. ML-команда реализует сервис по контракту v1.0
   ([ml-contract.md](../integrations/ml-contract.md) §12): четыре эндпоинта,
   чтение кадров из S3 по `storage_key`, канонические коды, уникальные
   `detection_id`, пустой список вместо ошибки.
2. Проверьте сервис контрактными тестами и смоук-примерами:

   ```bash
   cd backend && uv run pytest tests/contracts/test_ml_contract.py -m contract
   # curl-примеры: docs/integrations/ml-examples/
   ```

3. Переключите backend настройками окружения (`.env`):

   ```bash
   ML_PROVIDER=http
   ML_HTTP_BASE_URL=http://<ml-host>:8001
   # опционально: ML_HTTP_TIMEOUT_SECONDS, ML_HTTP_RETRIES, ML_HTTP_BACKOFF_SECONDS
   ```

4. Перезапустите backend и worker. Проверка: `GET /api/v1/ml/health` и
   `GET /api/v1/ml/model-info` (требуют аутентификации) проксируют
   `health()`/`model_info()` провайдера.

ML-сервис размещается в приватной сети и не публикуется наружу; аутентификация
backend ↔ ML в v1.0 отсутствует (доверенная сеть), см. ml-contract.md §14.

## Как добавить третий провайдер (новый код)

Пример: gRPC-провайдер, провайдер очереди задач инференса, локальный
ONNX-сервис-сайдкар.

1. **Реализация**: создайте `app/infrastructure/ml/<name>_provider.py` с классом,
   структурно реализующим протокол `MLProvider` (наследование не требуется —
   Protocol структурный). Все ошибки переводите в подклассы `MLProviderError`;
   валидируйте ответы так же строго, как `HTTPMLProvider`
   (`request_id`, bbox, уникальность `detection_id`).
2. **Настройка**: добавьте значение в `Literal` поля `ml_provider` в
   `app/config.py` и при необходимости параметры (`<NAME>_...`).
3. **Фабрика**: добавьте ветку в `build_ml_provider`
   (`app/infrastructure/ml/factory.py`).
4. **Тесты**:
   - unit по образцу `tests/unit/test_ml_providers.py`: успешные
     ответы, нарушения контракта, маппинг ошибок, повторы (для транспортного
     провайдера), детерминизм;
   - контрактные: `uv run pytest -m contract` — модели/схемы/примеры не должны
     расходиться;
   - интеграционные: pipeline с новым провайдером против реальной БД
     (`tests/integration/test_pipeline.py` использует mock/stub — добавьте
     параметризацию или отдельный тест).
5. **Документация**: обновите этот файл и таблицу провайдеров; если меняется
   формат обмена — это уже изменение контракта: новый `schema_version` и
   префикс `/v2`, синхронно `app/schemas/ml.py` + `contracts/ml/*.schema.json` +
   примеры + контрактные тесты (ml-contract.md §11).
6. `make lint` и полный прогон `./scripts/test.sh`.

## Правила

1. **Никаких ML-фреймворков в domain/application.** Домен не знает о существовании
   ML; `app/schemas/ml.py` — единственные «проводные» модели, и они не тянут
   ML-зависимости. Тяжёлые зависимости допустимы только в отдельном
   infrastructure-провайдере, если это осознанно (предпочтительно — вынести
   инференс во внешний сервис).
2. **Совместимость `schema_version`.** Проводные модели фиксируют
   `Literal["1.0"]`; любое другое значение — `MLContractError`. Аддитивные
   изменения (новые опциональные поля) допустимы в рамках 1.0; ломающие —
   только через новую версию контракта и новый префикс эндпоинтов.
3. **Идемпотентность.** `request_id` — ключ идемпотентности запроса;
   `detection_id` должен быть стабильным при повторной обработке того же
   `request_id` (backend дедуплицирует детекции по `(job_id, detection_id)`).
4. **Пустой результат — не ошибка.** `detections: []` при успешном ответе —
   штатный исход.
5. **Безопасность.** Не логировать байты изображений, presigned-ссылки и
   секреты; ML-сервис — только в приватной сети; доступ ML к хранилищу — по
   отдельным credentials с минимальными правами.