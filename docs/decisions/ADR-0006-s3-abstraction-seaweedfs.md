# ADR-0006: S3-абстракция; SeaweedFS вместо MinIO в dev / S3 abstraction; SeaweedFS replaces MinIO in dev

- **Статус / Status:** Accepted
- **Дата:** 2026-11-15 (проверка доступности MinIO: 2026-11-15)

## Контекст / Context

Нужно хранить оригиналы загрузок (до 2 ГиБ), кадры и кропы; выдавать
временные ссылки UI; давать ML-сервису чтение кадров по ключу. Бинарные данные
не должны попадать в PostgreSQL. Исторически dev-окружение использовало MinIO
как self-hosted S3. В 2026 году MinIO прекратил публичное распространение
community-версии. Проверено **2026-11-15**:

- Docker Hub репозиторий MinIO удалён — `docker pull minio/minio` отклоняется
  (pull denied);
- `dl.min.io` (бинарники) возвращает **410 Gone**;
- release-ассеты в GitHub-репозитории больше не публикуются.

То есть воспроизводимый dev/demo-стек на community MinIO собрать невозможно.

## Решение / Decision

1. **Абстракция `ObjectStorage`** (`application/interfaces/storage.py`):
   upload/download (bytes и file), delete, exists, presigned URL, metadata,
   close. Две реализации: `S3Storage` (boto3) и `LocalFilesystemStorage`
   (тесты/лёгкий dev). Выбор — `STORAGE_BACKEND` (`s3` | `local`).
2. **S3 API как протокол, а не конкретный сервер.** `S3Storage`: path-style
   addressing, signature v4, ретраи boto3, threadpool для sync-вызовов,
   нормализация ошибок в `StorageError`/`StorageObjectNotFoundError`.
   Любой S3-совместимый сервер подключается переменными окружения:
   `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_REGION`.
3. **В dev/demo — SeaweedFS** (`chrislusf/seaweedfs:latest`, S3 API на 9000)
   вместо MinIO. Тот же S3 API, тот же код клиента; бакет создаёт init-сервис
   `s3-init` (aws-cli `s3 mb`) + `ensure_bucket()` приложения при старте.
4. **Совместимость с MinIO сохранена**: если появится доступный образ/сборка
   MinIO (коммерческая лицензия, зеркало, собственная сборка), возврат —
   замена endpoint/credentials в окружении, без правок кода. AWS S3/Ceph RGW
   подключаются так же.
5. **Local-бэкенд** для тестов: защита от path traversal (`safe_join`),
   «presigned» = аутентифицированный путь `/api/v1/files/{key}`.

## Последствия / Consequences

- Dev/demo воспроизводим сегодня: образ SeaweedFS публично доступен, healthcheck
  и init бакета работают в compose и CI-скриптах.
- Нет vendor lock-in: переезд на AWS S3 или другой сервер — конфигурация, не код.
- Тесты не зависят от S3-сервера (local-бэкенд), но S3-реализация проверяется
  интеграционным тестом против реального S3 (`test_storage.py::test_s3_roundtrip`).
- Особенности SeaweedFS осознаны: S3-аутентификация в dev-конфигурации не
  enforced (ключи `minioadmin` — историческое имя, сервер их не проверяет);
  в production требуется сервер с аутентификацией и реальные секреты.
  Поведение некоторых S3-операций (multipart, versioning, lifecycle) может
  отличаться от AWS — используемый subset (put/get/head/delete/presign)
  совместим.
- Presigned-ссылки self-hosted сервера доступны только в сети, где resolving
  endpoint (для внешнего UI нужен доступный адрес — настройка окружения).

## Рассмотренные альтернативы / Alternatives considered

1. **Остаться на MinIO**: невозможно — публичная дистрибуция прекращена
   (проверено 2026-11-15); коммерческая лицензия для MVP не обоснована;
   отклонено.
2. **Только локальная ФС**: нет presigned-ссылок, нет паритета с production S3,
   ML-сервис не может читать кадры по ключу из общего хранилища; отклонено
   как основной бэкенд (оставлен для тестов).
3. **Другой self-hosted S3 (Ceph RGW, Garage, Zenko)**: тяжелее в эксплуатации
   (Ceph) или менее зрелый S3 subset; SeaweedFS — один лёгкий контейнер с
   полноценным S3 API; отклонено в пользу SeaweedFS.
4. **Сразу AWS S3 в dev**: внешняя зависимость, расходы, секреты у каждого
   разработчика, офлайн-разработка невозможна; отклонено для dev (production
   может использовать AWS S3 той же абстракцией).
5. **Нативные SDK облаков (Azure Blob/GCS) вместо S3-протокола**: lock-in и
   несколько реализаций; отклонено — S3 API де-факто стандарт.