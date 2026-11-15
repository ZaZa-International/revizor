# Contributing — MGTS Infrastructure Intelligence

Спасибо за вклад в проект. Этот документ описывает процесс разработки:
ветки, коммиты, требования к PR, review и границы модулей. Архитектура —
[ADR-0001](docs/decisions/ADR-0001-modular-monolith.md), тестирование —
[docs/development/testing.md](docs/development/testing.md).

## Окружение

- Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker Engine 29+ с Compose v2+.
- Первичная настройка: `make bootstrap` (проверка инструментов, `.env` из
  `.env.example`, `uv sync`, подъём db/redis/s3, миграции, ожидание бакета).
- Запуск стека: `make up` (фон) или `make dev` (hot reload).
- Демо-данные: `make seed`. OpenAPI: `make openapi`.

## Стратегия веток

- **`main`** — единственная долгоживущая ветка; всегда зелёная (CI passing),
  готова к деплою. Прямые push в `main` запрещены — только через PR.
- Рабочие ветки создаются от `main`:
  - `feature/<краткое-описание>` — новая функциональность;
  - `fix/<краткое-описание>` — исправление дефекта;
  - `docs/<...>`, `chore/<...>` — документация и обслуживание.
- Ветка живёт коротко: один PR — одна законченная задача; ребейз на `main`
  вместо merge-коммитов внутри ветки.
- Именование: латиница, kebab-case, без пробелов (`feature/asset-taxonomy-endpoint`).

## Conventional Commits

Формат: `<type>(<scope>): <описание>` (повелительное наклонение, без точки в конце).

| type | Когда |
|---|---|
| `feat` | новая функциональность |
| `fix` | исправление дефекта |
| `docs` | только документация |
| `test` | только тесты |
| `refactor` | рефакторинг без изменения поведения |
| `perf` | производительность |
| `chore` | обслуживание, зависимости, CI |
| `build` | сборка/образы |

Scope — модуль: `domain`, `api`, `pipeline`, `storage`, `ml`, `queue`, `auth`,
`dedup`, `risk`, `reviews`, `exports`, `ci`, `docs`. Примеры:

```
feat(domain): register street_cabinet asset type
fix(pipeline): skip already processed frames on retry
docs(decisions): add ADR-0013 on retention policy
```

Ломающие изменения: `feat(api)!: ...` + футер `BREAKING CHANGE: ...`.

## Требования к PR

PR обязан содержать:

1. **Тесты** на новое/изменённое поведение (правила —
   [testing.md](docs/development/testing.md)): unit для доменной логики,
   integration/api для БД/эндпоинтов, contract при изменении формата обмена.
   Все 262+ теста проходят: `./scripts/test.sh`.
2. **Линтеры и типы**: `make lint` (`ruff check`, `ruff format --check`,
   `mypy app`) — без ошибок и предупреждений. Автоформат: `make format`.
3. **Обновление документации**: затронутые docs (development/integrations/
   security/operations), при архитектурном решении — новый ADR; при изменении
   пользовательского поведения — запись в `CHANGELOG.md` (Unreleased).
4. **Миграции** (если меняется схема БД): Alembic-ревизия с рабочими
   `upgrade`/`downgrade` — CI проверяет roundtrip (`downgrade base` →
   `upgrade head`). Новые типы активов/дефектов миграции НЕ требуют
   (реестры в коде, [ADR-0010](docs/decisions/ADR-0010-taxonomy-as-code.md)).
5. **Описание PR**: что/зачем, как проверено, ссылки на issue/ADR; скриншоты
   для UI-затрагивающих изменений API.
6. **Без секретов**: `.env`, ключи, токены, реальные ПДн в коммитах запрещены
   (pre-commit `detect-private-key` + review). Медиа в тестах — только
   синтетические.

CI (`.github/workflows/ci.yml`): lint-typecheck, tests (unit отдельно, затем
integration/api/contract на service containers PostGIS+Redis), migration
roundtrip, docker build; `security.yml`: строгий `pip-audit`.

## Code review

- Минимум **один approve** от владельца затронутого модуля; изменения границ
  слоёв, контрактов (ML/frontend), схемы БД и безопасности — обязательный
  review архитектора/владельца контракта.
- Review проверяет: корректность и тесты, границы слоёв (ниже), именование,
  отсутствие секретов/ПДн, обновлённость docs/CHANGELOG, обратимость миграций.
- Комментарии — по существу кода, не автора; блокирующие замечания помечаются
  явно; автор отвечает на каждый комментарий (fix или обоснование).
- PR мержится после зелёного CI и resolve всех дискуссий; merge — squash с
  conventional-заголовком. Force-push в `main` запрещён.

## Definition of Done

- [ ] Код соответствует задаче; поведение проверено тестами (новый код покрыт)
- [ ] `./scripts/test.sh` — все тесты зелёные
- [ ] `make lint` — ruff check + format + mypy чистые
- [ ] Миграции (если есть) проходят roundtrip; новые типы — без миграций
- [ ] Документация обновлена (docs/, ADR при решении, CHANGELOG Unreleased)
- [ ] Контракты (ML JSON Schema/примеры, frontend-ответы) не сломаны или
      обновлены синхронно с тестами
- [ ] Секретов/ПДн в коде, тестах и логах нет; медиа синтетические
- [ ] PR описан, review пройден, CI зелёный, дискуссии закрыты

## Границы модулей (ownership)

Зависимости направлены внутрь: `api → application → domain ← infrastructure`
([ADR-0001](docs/decisions/ADR-0001-modular-monolith.md)). Нарушение границ —
блокирующее замечание на review.

| Модуль | Владеет | Запрещено |
|---|---|---|
| `app/domain/` | enum'ы, реестры типов, политики (dedup/risk/condition/review/state machine), геодоменные модели | Импорты FastAPI, SQLAlchemy, boto3, ML-фреймворков; I/O; обращение к БД/сети |
| `app/application/` | use cases (pipeline), сервисы, порты-Protocol (`MLProvider`, `ObjectStorage`, `JobQueue`) | Прямые импорты конкретных infrastructure-реализаций (только через порты/фабрики); HTTP-логика |
| `app/infrastructure/` | ORM-модели и репозитории, S3/local storage, RQ/inline queue, mock/http ML | Доменные решения (политики живут в domain); знание о FastAPI-роутерах |
| `app/api/` + `app/schemas/` | роутеры, RBAC-зависимости, Pydantic-схемы запросов/ответов, сериализация ORM → schema | **ORM-модели в ответах API** (только через `serializers.py`/схемы); бизнес-логика в роутерах; SQL в роутерах |
| `app/core/` | security, logging, metrics, exceptions, ratelimit, middleware | Доменная логика |
| `app/workers/` | точки входа RQ-задач, сборка pipeline | Дублирование логики pipeline |
| `contracts/ml/` + `app/schemas/ml.py` | контракт ML v1.0 (владелец — ML-интеграция) | Изменения без синхронного обновления схем/примеров/контрактных тестов и docs/integrations/ml-contract.md |
| `docs/decisions/` | ADR | Правка принятых ADR задним числом (новый ADR со статусом, superseding старый) |
| Миграции `backend/migrations/` | схема БД | Ручная правка применённых ревизий; необратимые downgrade |

Практические правила:

- Новый тип актива/дефекта — только через реестры
  ([adding-new-asset-type.md](docs/development/adding-new-asset-type.md),
  [adding-new-defect-type.md](docs/development/adding-new-defect-type.md)).
- Новый внешний сервис — новый порт в `application/interfaces/` +
  реализация в `infrastructure/` + фабрика + настройка; домен не меняется.
- Ошибки — только подклассы `AppError` из `app/core/exceptions.py` (единый
  конверт `{"error": {code, message, details, request_id}}`).
- Логи — structlog с контекстом (`request_id`/`job_id`/`actor_id`); секреты и
  ПДн не логируются (редакция по ключам — не повод класть их в сообщения).

## Документация

- Язык документации — русский (заголовки ADR могут быть двуязычными).
- Процессные документы: `docs/development/`; интеграции: `docs/integrations/`;
  безопасность: `docs/security/` + `SECURITY.md`; эксплуатация:
  `docs/operations/`; решения: `docs/decisions/ADR-XXXX-*.md`.
- CHANGELOG — формат [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
  версии — [SemVer](https://semver.org/lang/ru/).