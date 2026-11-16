# Аутентификация и авторизация

Схема: **JWT Bearer** (HS256). Токен выдаётся `POST /api/v1/auth/login`,
передаётся в заголовке `Authorization: Bearer <access_token>`. Сессий и cookie
нет; CORS настроен на явные origin (`CORS_ORIGINS`, по умолчанию
`http://localhost:3000` и `http://localhost:5173`), `*` с credentials запрещён.

## Login flow

```bash
curl -s http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username": "operator1", "password": "…"}'
```

Ответ 200 ([пример](../../contracts/examples/api/login-response.json)):

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs…",
  "token_type": "bearer",
  "expires_in_minutes": 60,
  "user": {"id": "…", "username": "operator1", "email": null, "role": "OPERATOR", "is_active": true, "created_at": "…"}
}
```

- `username` 1…64 символа, `password` 1…256 символов; неверная пара → 401
  `authentication_failed` (без уточнения, что именно неверно).
- Время жизни токена — `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (по умолчанию **60
  минут**). Claims: `sub` (id пользователя), `role`, `exp`, `iat`, `jti`.
- **Роль проверяется по БД на каждом запросе**, а не из claim'а токена:
  изменение роли/деактивация пользователя действуют немедленно.
- Первый администратор создаётся при старте (bootstrap), если задан
  `BOOTSTRAP_ADMIN_PASSWORD` и пользователей ещё нет. Управление
  пользователями через API в MVP не предусмотрено.

### Использование токена

```bash
TOKEN="eyJhbGciOi…"
curl -s http://localhost:8000/api/v1/assets \
  -H "Authorization: Bearer $TOKEN"
```

### Logout и отзыв токена

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/logout \
  -H "Authorization: Bearer $TOKEN"
# → {"message": "logged out"}
```

`jti` токена помещается в Redis-denylist (`jwt:deny:{jti}`) с TTL до естественного
`exp`. Последующие запросы с этим токеном → 401 `authentication_failed`
("Token revoked"). Особенности:

- Logout требует доступного Redis (иначе ошибка).
- При недоступности Redis проверка denylist **fail-open**: уже выданные токены
  остаются валидными до истечения срока (доступность важнее отзыва; событие
  логируется). Это осознанная политика MVP.
- Refresh-токенов нет: после истечения — повторный login.

## Матрица ролей

Роли: `ADMIN`, `OPERATOR`, `VIEWER`, `SERVICE`. `SERVICE` — машинные интеграции
(например, выгрузки), по правам эквивалентна OPERATOR.

| Группа endpoint'ов | ADMIN | OPERATOR | SERVICE | VIEWER |
|---|---|---|---|---|
| `POST /auth/login`, `/health*` | без auth | без auth | без auth | без auth |
| `GET /auth/me`, `POST /auth/logout` | ✔ | ✔ | ✔ | ✔ |
| Чтение списков/карточек (assets, observations, defects, reviews, jobs, routes, uploads, analytics, map, ml) | ✔ | ✔ | ✔ | ✔ |
| Экспорты CSV/XLSX (`/exports/*`) | ✔ | ✔ | ✔ | ✔ |
| Мутации: `POST/DELETE /uploads`, `POST /jobs`, retry/cancel, `PATCH /assets`, `PATCH /defects`, `POST /reviews`, `POST /routes` | ✔ | ✔ | ✔ | ✘ 403 |
| **Медиа**: `presigned_url` загрузок, `image_url`/`crop_url` наблюдений | ✔ | ✔ | ✔ | **null** (URL не выдаются) |
| `GET /api/v1/files/{key}` (local storage) | ✔ | ✔ | ✔ | ✘ 403 |
| `DELETE /uploads/{id}` | любой upload | только свой | только свой | ✘ 403 |

VIEWER видит все данные реестра, но **не получает доступа к исходным
изображениям** (privacy-политика, см. [privacy.md](../security/privacy.md)):
поля URL приходят `null`, прямое скачивание через `/files` запрещено.

## Rate limits

Лимиты скользящего окна (Redis; при недоступности Redis — in-memory fallback
в пределах процесса). При превышении — **429 `rate_limited`** с заголовком
`Retry-After` (секунды до конца окна, обычно 60).

| Действие | Ключ | Лимит (по умолчанию) | Переменная |
|---|---|---|---|
| Login | IP клиента | 10/мин | `RATE_LIMIT_LOGIN_PER_MINUTE` |
| Login | username | 20/мин | `RATE_LIMIT_LOGIN_PER_USERNAME_PER_MINUTE` |
| Upload | пользователь | 30/мин | `RATE_LIMIT_UPLOAD_PER_MINUTE` |

Per-username лимит защищает от глобального lockout'а за прокси и от перебора
пароля по одному аккаунту с разных IP.

## Семантика 401 / 403 / 429

| Статус | Код | Когда | Что делать клиенту |
|---|---|---|---|
| 401 | `authentication_failed` | Нет/невалидный/просроченный/отозванный токен; пользователь неактивен | Повторный login; при 401 после logout — нормально |
| 403 | `permission_denied` | Роли не хватает (например, VIEWER делает PATCH) или медиа недоступно роли | Не повторять с тем же токеном; показать ограничение UI |
| 429 | `rate_limited` | Превышен лимит login/upload | Ждать `Retry-After` секунд, затем повторить; экспоненциальный backoff |

## Заметки по безопасности

- Токены и пароли **не логируются** (redaction-процессор + запрет логирования
  секретов на уровне кода); в логах только `request_id`, коды ошибок, метрики.
- Пароли — Argon2id (OWASP-параметры). JWT: фиксированный алгоритм HS256,
  обязательные `exp`/`sub`, проверка типа токена.
- В production пустой/placeholder `JWT_SECRET_KEY` (< 32 символов) запрещён
  валидатором конфигурации — сервер не стартует.
- Presigned-ссылки на медиа: только GET, TTL `S3_PRESIGN_EXPIRES_SECONDS`
  (по умолчанию 3600 с), подписываются публичным endpoint'ом
  (`S3_PUBLIC_ENDPOINT_URL`). Не кэшируйте их дольше TTL; при replay
  идемпотентных запросов ссылки перегенерируются.
- Каждый ответ несёт `x-request-id` (принимается и из запроса, обрезается до
  64 символов) — используйте для корреляции с поддержкой.
- Security headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Cache-Control: no-store` на `/api/*`; HSTS выставляется на reverse proxy.

См. также: [errors.md](errors.md), [workflows.md](workflows.md),
[ADR-0012 security model](../decisions/ADR-0012-security-model.md).
