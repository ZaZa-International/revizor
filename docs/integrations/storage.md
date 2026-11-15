# Объектное хранилище

Бинарные файлы (оригиналы загрузок, кадры, кропы) хранятся в объектном
хранилище за абстракцией `ObjectStorage`. В PostgreSQL попадают только ключи и
метаданные (`stored_files`, `uploads`) — никаких BLOB в БД.

Решение об абстракции и выборе S3-совместимого сервера для dev —
[ADR-0006](../decisions/ADR-0006-s3-abstraction-seaweedfs.md).

## Протокол ObjectStorage

`backend/app/application/interfaces/storage.py`:

```python
@runtime_checkable
class ObjectStorage(Protocol):
    async def upload(self, key: str, data: bytes, content_type: str) -> None: ...
    async def upload_file(self, key: str, path: str, content_type: str) -> None: ...
    async def download(self, key: str) -> bytes: ...
    async def download_to_file(self, key: str, path: str) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def generate_presigned_url(
        self, key: str, expires_seconds: int = 3600, method: str = "GET"
    ) -> str: ...
    async def get_metadata(self, key: str) -> ObjectMetadata: ...
    async def close(self) -> None: ...

@dataclass(frozen=True)
class ObjectMetadata:
    size: int
    content_type: str
    checksum_sha256: str | None = None
```

Выбор реализации — `build_storage(settings)`
(`app/infrastructure/storage/factory.py`) по `STORAGE_BACKEND` (`s3` | `local`).
Ошибки нормализуются в `StorageError` / `StorageObjectNotFoundError`
(`app/core/exceptions.py`).

## S3Storage

`app/infrastructure/storage/s3.py`. Работает с **любым S3-совместимым сервером**
(SeaweedFS, MinIO, AWS S3, Ceph RGW, …) через boto3.

- boto3 синхронный — все вызовы выполняются в threadpool (`anyio.to_thread`),
  async API не блокируется.
- Клиент: `signature_version="s3v4"`, **path-style addressing**
  (`s3={"addressing_style": "path"}`) — обязательно для self-hosted серверов без
  wildcard DNS; собственные ретраи boto3 `max_attempts=2, mode="standard"`.
- `ensure_bucket()`: `head_bucket`, при отсутствии — `create_bucket`
  (вызывается при старте приложения).
- Presigned URL: `generate_presigned_url` для `GET` (`get_object`) и `PUT`
  (`put_object`); срок — `expires_seconds` либо настройка
  `S3_PRESIGN_EXPIRES_SECONDS` (по умолчанию 3600 с).
- Маппинг ошибок: `ClientError` с кодом `404`/`NoSuchKey`/`NotFound` →
  `StorageObjectNotFoundError`; прочие → `StorageError` (в лог — только код
  ошибки и операция, не содержимое).
- `get_metadata` возвращает размер и content-type; `checksum_sha256` в S3-режиме
  не вычисляется (None) — контрольные суммы загрузок хранятся в `uploads`.

Настройки (`.env`):

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `STORAGE_BACKEND` | `s3` | `s3` или `local` |
| `S3_ENDPOINT_URL` | `http://localhost:9000` | endpoint S3 API (в compose — `http://s3:9000`) |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | `minioadmin` / `minioadmin` | credentials (dev-значения, историческое имя; в production заменить) |
| `S3_BUCKET` | `mgts-infra` | бакет |
| `S3_REGION` | `us-east-1` | регион (для self-hosted — произвольный) |
| `S3_PRESIGN_EXPIRES_SECONDS` | 3600 | TTL presigned-ссылок |

## LocalFilesystemStorage

`app/infrastructure/storage/local.py`. Для тестов и лёгкой разработки
(`STORAGE_BACKEND=local`, корень — `STORAGE_LOCAL_PATH`).

- **Защита от path traversal** — `safe_join(root, key)`: ключ не может быть
  пустым, начинаться с `/`, содержать сегмент `..` или `\`; после `resolve()`
  путь обязан оставаться внутри корня. Нарушение → `ValidationAppError`.
- Content-type хранится в sidecar-файле `<key>.meta`; `get_metadata` считает
  SHA-256 файла.
- Presigned-ссылок нет: `generate_presigned_url` возвращает относительный путь
  **`/api/v1/files/{key}`**. Этот эндпоинт (`app/api/v1/files.py`) требует
  аутентификации (Bearer) и отдаёт файл через временную копию с удалением после
  ответа. То есть «ссылка» работает только внутри API с токеном, а не как
  публичный URL.
- Отсутствующий объект → `StorageObjectNotFoundError`.

## Раскладка ключей

| Префикс | Шаблон | Кто пишет |
|---|---|---|
| `uploads/` | `uploads/{upload_id}/{safe_filename}` | `UploadService.create_upload` (оригинал; имя санитизируется, ≤ 200 символов) |
| `frames/` | `frames/{job_id}/{frame_index:06d}.jpg` | `ProcessingPipeline._process_frame` (кадр после quality gate и privacy-фильтра) |
| `crops/` | `crops/{job_id}/{detection_id}.jpg` | `ProcessingPipeline._store_crop` (кроп детекции, JPEG q90) |
| `exports/` | — | **В MVP не используется**: экспорты CSV/XLSX генерируются в памяти и отдаются потоком как HTTP-вложение (`/api/v1/exports/*`), в хранилище не сохраняются |

Пример: `frames/3f2a…/000042.jpg`, `crops/3f2a…/8b1c….jpg`.

## Жизненный цикл объектов

`StorageObjectKind` (`app/domain/enums.py`) — тип объекта в `stored_files.kind`:

| Kind | Что это | Когда создаётся | Анонимизация (MVP) | Удаление |
|---|---|---|---|---|
| `ORIGINAL` | Исходная загрузка | При загрузке файла | не применяется | `DELETE /api/v1/uploads/{id}` — только если нет связанных задач; иначе 409 |
| `FRAME` | Кадр задачи | При обработке кадра | `NOT_APPLIED` (NoopPrivacyFilter) | Каскадно с записями БД; автоматического TTL нет |
| `CROP` | Кроп детекции | При сохранении наблюдения | `NOT_APPLIED` (явно) | Вместе с наблюдением; автоматического TTL нет |
| `ANONYMIZED` | Анонимизированная версия | **Зарезервировано**, в MVP не создаётся | — | — |
| `EXPORT` | Сохранённый экспорт | **Зарезервировано**, в MVP не создаётся (экспорты потоковые) | — | — |

Автоматических политик retention/lifecycle в MVP нет — рекомендации по срокам
хранения и удалению см. в [privacy.md](../security/privacy.md).

## Dev-хранилище: SeaweedFS вместо MinIO

В `docker-compose.yml` сервис `s3` — **SeaweedFS** (`chrislusf/seaweedfs:latest`,
S3 API на порту 9000). Причина: MinIO прекратил публичное распространение
community-образов и бинарников. Проверено **2026-11-15**:

- Docker Hub репозиторий MinIO удалён — `docker pull` отклоняется;
- `dl.min.io` возвращает **410 Gone**;
- release-ассеты в GitHub больше не публикуются.

Подробности и альтернативы — [ADR-0006](../decisions/ADR-0006-s3-abstraction-seaweedfs.md).

Практические следствия:

- **Совместимость**: SeaweedFS реализует тот же S3 API (PutObject/GetObject/
  HeadObject/DeleteObject/presigned URL, path-style). Код `S3Storage` не делал
  никаких предположений о MinIO — замена сервера не потребовала изменений кода.
- **Замена сервера**: любой S3-совместимый сервер подключается переменными
  окружения (`S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`,
  `S3_REGION`). Вернуться на MinIO (например, на коммерческий образ/сборку) или
  уйти в AWS S3 можно без правок кода; для AWS S3 может понадобиться
  virtual-hosted addressing — сейчас зафиксирован path-style, что AWS тоже
  поддерживает для совместимости.
- **Credentials**: dev-значения `minioadmin/minioadmin` — историческое имя из
  `.env.example`. SeaweedFS S3 в dev-конфигурации работает без проверки
  подписи/аутентификации; в production настройте аутентификацию на стороне
  S3-сервера и замените ключи.
- **Инициализация бакета**: сервис `s3-init` (`amazon/aws-cli`) после
  healthy-статуса `s3` выполняет `aws --endpoint-url http://s3:9000 s3 mb
  s3://mgts-infra` (идемпотентно, `|| true`). Приложение дополнительно вызывает
  `ensure_bucket()` при старте.
- **Тесты**: `scripts/test.sh` поднимает `s3`/`s3-init` для паритета окружения,
  но сами тесты используют `STORAGE_BACKEND=local` во временном каталоге —
  S3-реализация проверяется отдельными интеграционными тестами
  (`tests/integration/test_storage.py`).

## Связанные документы

- [ADR-0006](../decisions/ADR-0006-s3-abstraction-seaweedfs.md) — решение об абстракции и SeaweedFS
- [privacy.md](../security/privacy.md) — доступ к файлам, анонимизация, retention
- [ml-contract.md](ml-contract.md) — ML читает кадры по `storage_key` из того же хранилища
- [../operations/local-development.md](../operations/local-development.md) — запуск окружения