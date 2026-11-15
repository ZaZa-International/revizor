# Добавление нового типа актива

Типы активов — **расширяемый реестр в коде**, а не перечисление в БД. Колонки
`asset_type`/`object_type` в PostgreSQL имеют тип `VARCHAR`; валидация против
реестра выполняется на границах приложения. Поэтому новый тип актива
**не требует миграции БД** (см. [ADR-0010](../decisions/ADR-0010-taxonomy-as-code.md)).

Единственный источник истины: `backend/app/domain/assets/taxonomy.py`.

## Шаг 1. Зарегистрируйте AssetTypeDef

В конце `backend/app/domain/assets/taxonomy.py` добавьте:

```python
register_asset_type(
    AssetTypeDef(
        code="street_cabinet",          # snake_case, латиница; хранится в БД и в ML-контракте
        display_name="Уличный шкаф",    # человекочитаемое имя (RU)
        impact_factor=0.85,             # вес важности типа в risk scoring, (0, 1]
        dedup_radius_m=10.0,            # радиус поиска кандидатов дедупликации, метры
    )
)
```

Поля `AssetTypeDef`:

| Поле | Смысл | Где используется |
|---|---|---|
| `code` | Канонический код типа | БД (`assets.asset_type`, `observations.object_type`), ML-контракт `object_type`, фильтры API |
| `display_name` | Отображаемое имя | Справочная информация для UI/экспорта |
| `impact_factor` | Множитель важности в формуле приоритета | `app/domain/risk/scoring.py` (`assess_risk`); для неизвестного типа fallback 0.5 |
| `dedup_radius_m` | Радиус (м) поиска кандидатов того же типа | `app/application/services/deduplication.py`; общий fallback — `DEDUP_RADIUS_M` (15 м) |

Текущий реестр: `telecom_well` (1.0, 10 м), `pole` (0.8, 12 м),
`telecom_cabinet` (0.9, 8 м), `cable_line` (0.7, 25 м), `other` (0.5, 15 м).

Рекомендации по выбору значений:

- `impact_factor`: насколько критичен тип для сети. Колодец с открытой крышкой
  опаснее провисания кабеля — отсюда 1.0 против 0.7. Значение > 1 не запрещено
  типом, но ломает шкалу приоритета 0..100 — не делайте так.
- `dedup_radius_m`: физический размер объекта + погрешность GPS. Крупные/линейные
  объекты — больше радиус; точечные компактные — меньше.

## Шаг 2. (Опционально) Связи с состояниями и дефектами

- Если для нового типа актуальны специфичные дефекты — добавьте их в реестр
  дефектов с `applicable_asset_types`, содержащим новый код
  (см. [adding-new-defect-type.md](adding-new-defect-type.md)).
- Маппинг «состояние → дефект» (`CONDITION_DEFECT_MAP` в
  `app/domain/observations/condition.py`) работает по классам состояния, а не
  по типам активов; трогайте его, только если появляется новый класс состояния.
- Универсальные состояния (`ok`, `damaged`, `unknown`) уже нормализуются для
  любого типа — дополнительных действий не нужно.

## Шаг 3. ML-контракт менять НЕ нужно

`object_type` в контракте v1.0 — **открытая строка** (1..64 символа), а не enum
(`contracts/ml/inference-response.schema.json`, `app/schemas/ml.py`). Канонические
коды в `docs/integrations/ml-contract.md` §4 — рекомендация, а не ограничение.

- Backend принимает от ML любой `object_type` и сохраняет как есть; risk scoring
  для незарегистрированного кода использует fallback `impact_factor = 0.5`.
- Чтобы новый тип участвовал в скоринге корректно и проходил валидацию
  review-корректировок (`is_known_asset_type`), регистрация в реестре обязательна.
- Mock-провайдер автоматически подхватывает реестр (`all_asset_types()`) —
  синтетические детекции начнут включать новый тип без правок mock.
- Реальный ML-сервис должен начать возвращать новый код самостоятельно;
  согласуйте это с ML-командой и обновите список канонических кодов в
  `docs/integrations/ml-contract.md` (документация, не схема).

## Шаг 4. Миграция не нужна

`assets.asset_type`, `observations.object_type`, `defects.defect_type` —
`VARCHAR`. Никаких `ALTER TYPE`, никаких новых записей в справочные таблицы.
Проверьте только, что длина кода укладывается в ограничения колонок
(например, `String(64)`).

## Шаг 5. Тесты

Минимальный набор (см. [testing.md](testing.md)):

1. **Unit**: тест реестра — `get_asset_type("street_cabinet")` возвращает
   определение, `is_known_asset_type` истинно; тест risk scoring с новым
   `impact_factor` (по образцу `tests/unit/test_risk_scoring.py`).
2. **Unit dedup**: радиус нового типа учитывается политикой
   (по образцу `tests/unit/test_dedup_policy.py`).
3. **API**: фильтр `GET /api/v1/assets?asset_type=street_cabinet` работает
   (по образцу `tests/api/test_assets_api.py`).
4. Если тип попадает в демо-сценарий — проверьте контрактные тесты
   (`pytest -m contract`): они не должны сломаться от нового кода.

Запуск: `uv run pytest -m unit && ./scripts/test.sh -m "api or contract"`,
затем `make lint`.

## Шаг 6. (Опционально) Демо-данные

Если тип должен присутствовать в демо: добавьте записи в `scripts/seed_demo.py`
(массив сценариев «тип/состояние/severity/confidence») и перезапустите
`make seed`. Сид использует только канонические коды из реестра.

## Шаг 7. Frontend

Отдельных изменений на frontend не требуется: типы приходят через API
(значения `asset_type` в ответах `/api/v1/assets`, фильтры, карта, аналитика).
Специализированного эндпоинта-справочника типов в MVP нет — UI отображает коды
и `display_name` активов из данных. Если UI нужен полный справочник типов с
`display_name`/`impact_factor`, это отдельная задача на новый эндпоинт
(аддитивное изменение API).

## Чек-лист

- [ ] `AssetTypeDef` зарегистрирован в `taxonomy.py` (code, display_name, impact_factor, dedup_radius_m)
- [ ] При необходимости — дефекты с `applicable_asset_types` и маппинг состояний
- [ ] ML-команда уведомлена о новом каноническом коде (контракт не меняется)
- [ ] Миграции НЕ создавались
- [ ] Тесты unit/api добавлены и проходят; `make lint` чистый
- [ ] При необходимости обновлён `scripts/seed_demo.py`
- [ ] Список канонических кодов в `docs/integrations/ml-contract.md` обновлён