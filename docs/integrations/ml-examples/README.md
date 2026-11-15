# curl-примеры обращения к ML-сервису

Примеры используют эталонные тела из `contracts/ml/examples/` (корень
репозитория). Полный контракт — [../ml-contract.md](../ml-contract.md).

Базовый URL задаётся переменной окружения `ML_BASE_URL`
(по умолчанию `http://localhost:8001` — адрес ML-сервиса в приватной сети).

## Смоук-скрипты

```bash
export ML_BASE_URL=http://localhost:8001

./health.sh        # GET  /v1/health
./model-info.sh    # GET  /v1/model-info
./infer.sh         # POST /v1/infer        (examples/request.json)
./infer-batch.sh   # POST /v1/infer/batch  (examples/batch-request.json)
```

## health

```bash
curl -sS "$ML_BASE_URL/v1/health"
```

Ожидаемый ответ — `contracts/ml/health.schema.json`, например:

```json
{"status": "ok", "model_loaded": true, "provider": "http", "details": {}}
```

## model-info

```bash
curl -sS "$ML_BASE_URL/v1/model-info"
```

Ожидаемый ответ — `contracts/ml/model-info.schema.json`:

```json
{"name": "infrastructure-detector", "version": "1.2.0", "schema_version": "1.0"}
```

## Одиночный инференс

```bash
curl -sS -X POST "$ML_BASE_URL/v1/infer" \
  -H 'Content-Type: application/json' \
  --data @contracts/ml/examples/request.json
```

- Успех: `contracts/ml/examples/response.json` (детекции) или
  `contracts/ml/examples/response-empty.json` (пустой результат — валидный
  исход, HTTP 200).
- Ошибка модели: HTTP 422/400 с конвертом `contracts/ml/examples/error.json`
  (`error.code = "inference_failed"` → backend поднимет `MLInferenceError`).
- Прочие 4xx → `MLContractError`, 5xx/таймауты → повторы, затем
  `MLUnavailableError`/`MLTimeoutError` (см. §6 и §10 контракта).

## Batch-инференс (частичные ошибки)

```bash
curl -sS -X POST "$ML_BASE_URL/v1/infer/batch" \
  -H 'Content-Type: application/json' \
  --data @contracts/ml/examples/batch-request.json
```

Ожидаемый ответ — `contracts/ml/examples/batch-response-partial.json`:
первый кадр `OK` с полным ответом, второй `ERROR` с `{code, message}`.
Ошибка одного кадра не прерывает остальные.

## Проверка ответов против JSON Schema

```bash
cd backend
uv run pytest tests/contracts/test_ml_contract.py -m contract -q
```

Тесты проверяют все примеры против схем draft 2020-12 и roundtrip через
Pydantic-модели `app/schemas/ml.py`.
