# Добавление нового типа дефекта

Типы дефектов, как и типы активов, — **реестр в коде** над `VARCHAR`-колонками
(`defects.defect_type`, `String(64)`). Новый тип дефекта **не требует миграции
БД** (см. [ADR-0010](../decisions/ADR-0010-taxonomy-as-code.md)).

Источники истины:

- `backend/app/domain/defects/taxonomy.py` — реестр типов дефектов;
- `backend/app/domain/observations/condition.py` — нормализация состояний ML и
  маппинг «состояние → тип дефекта».

## Шаг 1. Зарегистрируйте DefectTypeDef

В конце `backend/app/domain/defects/taxonomy.py` добавьте:

```python
register_defect_type(
    DefectTypeDef(
        code="cabinet_corrosion",                 # snake_case, латиница, <= 64 символов
        display_name="Коррозия корпуса шкафа",    # человекочитаемое имя (RU)
        default_severity=3,                       # 1..5, используется как ориентир
        applicable_asset_types=("telecom_cabinet",),  # к каким типам активов применим
    )
)
```

Поля `DefectTypeDef`:

| Поле | Смысл |
|---|---|
| `code` | Канонический код; хранится в `defects.defect_type`, используется в review-корректировках и API-фильтрах |
| `display_name` | Отображаемое имя |
| `default_severity` | Severity по умолчанию (1 — минимальная, 5 — критическая). Фактическая severity наблюдения берётся из ML-ответа или из `CONDITION_DEFAULT_SEVERITY`; это поле — справочный ориентир для UI/аналитики |
| `applicable_asset_types` | Кортеж кодов активов, для которых дефект смыслен. Пустой кортеж (как у `other`) = универсальный дефект. Поле декларативное: runtime-валидация применимости в MVP не выполняется, соблюдайте соответствие при регистрации и в review-логике |

Текущий реестр: `missing_cover` (5), `damaged_cover` (4), `well_subsidence` (4),
`cabinet_damage` (3), `cabinet_door_open` (3), `pole_tilt` (4), `pole_damage` (4),
`cable_break` (5), `cable_sag` (3), `other` (2, универсальный).

## Шаг 2. Свяжите состояние ML с новым дефектом

Pipeline создаёт дефект автоматически: `condition_class` из ML-ответа
нормализуется, затем по `CONDITION_DEFECT_MAP` определяется тип дефекта
(`app/application/use_cases/processing/pipeline.py`, `_upsert_defect`). Чтобы
новый дефект появлялся из предсказаний, обновите `condition.py`:

1. **`CONDITION_ALIASES`** — добавьте канонический класс состояния и его алиасы
   (ML может прислать синонимы):

   ```python
   "corrosion": "corroded",
   "rust": "corroded",
   "corroded": "corroded",
   ```

2. **`CONDITION_DEFAULT_SEVERITY`** — severity по умолчанию для нового класса
   (используется, когда ML прислал `severity = null`):

   ```python
   "corroded": 3,
   ```

3. **`CONDITION_DEFECT_MAP`** — маппинг класса состояния в код дефекта:

   ```python
   "corroded": "cabinet_corrosion",
   ```

`CANONICAL_CONDITIONS` пересчитывается автоматически из значений
`CONDITION_ALIASES` (+ `unknown`). Неизвестные ML-значения нормализуются в
`unknown` и дефект не создают — это безопасное поведение по умолчанию.

Если дефект создаётся только вручную (через review/редактирование), шаги 2.1–2.3
не нужны: достаточно реестра и валидации `is_known_defect_type` в
`ReviewService` (она уже работает против реестра).

## Шаг 3. ML-контракт менять НЕ нужно

`condition_class` в контракте v1.0 — открытая строка (≤ 64 символов), не enum.
Backend нормализует алиасы и неизвестные значения сам. Реальный ML-сервис может
начать возвращать новый класс без изменения `schema_version`; рекомендуется
согласовать код с ML-командой и дополнить таблицу канонических состояний в
`docs/integrations/ml-contract.md` §4 (документация, не схема).

Mock-провайдер использует `CANONICAL_CONDITIONS` и автоматически начнёт
генерировать новое состояние.

## Шаг 4. Миграция не нужна

Колонки `defect_type` — `VARCHAR(64)`. Проверьте только длину кода.
Severity-ограничения (`1..5`) уже зафиксированы `CheckConstraint` в БД —
`default_severity` обязан попадать в диапазон.

## Шаг 5. Тесты

1. **Unit**: `get_defect_type`/`is_known_defect_type` для нового кода;
   `normalize_condition` для новых алиасов; `default_severity_for_condition`;
   `defect_type_for_condition` (по образцу `tests/unit/test_condition.py`).
2. **Integration**: pipeline создаёт/обновляет дефект нового типа при
   соответствующем состоянии (по образцу `tests/integration/test_pipeline.py`,
   стаб `tests/fixtures/ml_stub.py` можно настроить на новый `condition_class`).
3. **API**: review-корректировка `corrected_defect_type` новым кодом проходит
   валидацию; фильтр `GET /api/v1/defects?defect_type=...` работает
   (по образцу `tests/api/test_reviews_api.py`).

Запуск: `uv run pytest -m unit && ./scripts/test.sh -m "integration or api"`,
затем `make lint`.

## Шаг 6. (Опционально) Демо-данные и frontend

- `scripts/seed_demo.py` — добавьте сценарии с новым состоянием, если дефект
  должен быть в демо (`make seed`).
- Frontend подхватывает дефекты через API (`/api/v1/defects`, карточка актива,
  аналитика); отдельных изменений не требуется. Как и для типов активов,
  справочного эндпоинта типов дефектов в MVP нет.

## Чек-лист

- [ ] `DefectTypeDef` зарегистрирован (code, display_name, default_severity 1..5, applicable_asset_types)
- [ ] При автоматическом создании: алиасы + severity + `CONDITION_DEFECT_MAP` в `condition.py`
- [ ] ML-команда уведомлена о новом классе состояния (контракт не меняется)
- [ ] Миграции НЕ создавались
- [ ] Тесты unit/integration/api добавлены и проходят; `make lint` чистый
- [ ] При необходимости обновлён `scripts/seed_demo.py`
- [ ] Таблица состояний в `docs/integrations/ml-contract.md` обновлена