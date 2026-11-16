"""Domain enumerations shared across the system.

These are pure-Python enums with no dependency on FastAPI/SQLAlchemy/ML.
DB models map to these via SQLAlchemy Enum with native PostgreSQL types.
"""
# ruff: noqa: RUF002  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Роль пользователя, определяющая права доступа (RBAC).

    ADMIN — полный доступ, включая управление чужими загрузками и удаление.
    OPERATOR — загрузки, jobs, reviews, PATCH реестров, доступ к медиафайлам.
    VIEWER — только чтение реестров и аналитики; медиа-ссылки скрыты (null),
    мутации запрещены (403).
    SERVICE — машинная роль для интеграций; права как у OPERATOR.
    """

    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"
    SERVICE = "SERVICE"


class MediaType(StrEnum):
    """Тип загруженного медиафайла (определяется по magic bytes).

    IMAGE — изображение (jpeg/png/webp); обрабатывается как один кадр.
    VIDEO — видео (mp4/avi/mov/webm); кадры извлекаются с заданным интервалом.
    """

    IMAGE = "IMAGE"
    VIDEO = "VIDEO"


class GeolocationStatus(StrEnum):
    """Достоверность геопривязки объекта/наблюдения.

    CONFIRMED — координаты получены из GPS с приемлемой точностью
    (accuracy_m ≤ порога, по умолчанию 50 м).
    ESTIMATED — координаты оценочные (низкая точность GPS, интерполяция трека).
    UNAVAILABLE — GPS отсутствовал; координаты не выдумываются (null).
    INVALID — координаты признаны некорректными (выход за диапазоны,
    противоречивые данные трека).
    """

    CONFIRMED = "CONFIRMED"
    ESTIMATED = "ESTIMATED"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


class GeolocationSource(StrEnum):
    """Источник координат объекта/наблюдения.

    GPS — данные GPS-трека из metadata загрузки.
    MANUAL — координаты заданы оператором вручную (PATCH location).
    MAP_MATCHING — привязка к карте/дорожной сети (зарезервировано).
    VISUAL — определено визуально по кадру (зарезервировано).
    UNKNOWN — источник не определён.
    """

    GPS = "GPS"
    MANUAL = "MANUAL"
    MAP_MATCHING = "MAP_MATCHING"
    VISUAL = "VISUAL"
    UNKNOWN = "UNKNOWN"


class LifecycleStatus(StrEnum):
    """Жизненный цикл физического объекта в реестре.

    ACTIVE — объект эксплуатируется и наблюдается.
    INACTIVE — объект временно не эксплуатируется.
    RETIRED — объект выведен из эксплуатации (демонтирован).
    UNKNOWN — состояние не определено (значение по умолчанию).
    """

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    RETIRED = "RETIRED"
    UNKNOWN = "UNKNOWN"


class JobStatus(StrEnum):
    """Жизненный цикл processing job.

    PENDING — job создан, ещё не поставлен в очередь.
    QUEUED — job в очереди RQ, ожидает worker.
    PROCESSING — worker обрабатывает кадры (прогресс в progress/current_stage).
    COMPLETED — все кадры обработаны успешно (терминальный).
    PARTIALLY_COMPLETED — часть кадров REJECTED/FAILED; допустим retry.
    FAILED — job завершился ошибкой (error_code/error_message); допустим retry.
    CANCELLED — отменён оператором (кооперативная отмена); допустим retry.
    «Зависшие» PROCESSING (без прогресса дольше rq_job_timeout + grace)
    автоматически переводятся в FAILED и могут быть перезапущены.
    """

    PENDING = "PENDING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProcessingStage(StrEnum):
    """Текущая стадия pipeline обработки job (информационная, для прогресса).

    VALIDATION — проверка загрузки и метаданных.
    STORAGE — сохранение исходного файла в хранилище.
    FRAME_EXTRACTION — извлечение кадров из видео.
    QUALITY_GATE — отбраковка размытых/засвеченных кадров.
    PRIVACY_FILTER — анонимизация (если включена; иначе NOT_APPLIED).
    INFERENCE — ML-детекции объектов на кадрах.
    NORMALIZATION — приведение детекций к доменной модели.
    TRACKING — связывание детекций одного объекта между кадрами.
    GEOLOCATION — привязка кадров к GPS-треку.
    DEDUPLICATION — сопоставление с существующими активами.
    RISK_SCORING — расчёт приоритета объектов.
    PERSISTENCE — запись наблюдений/дефектов/истории.
    COMPLETED — pipeline завершён.
    """

    VALIDATION = "VALIDATION"
    STORAGE = "STORAGE"
    FRAME_EXTRACTION = "FRAME_EXTRACTION"
    QUALITY_GATE = "QUALITY_GATE"
    PRIVACY_FILTER = "PRIVACY_FILTER"
    INFERENCE = "INFERENCE"
    NORMALIZATION = "NORMALIZATION"
    TRACKING = "TRACKING"
    GEOLOCATION = "GEOLOCATION"
    DEDUPLICATION = "DEDUPLICATION"
    RISK_SCORING = "RISK_SCORING"
    PERSISTENCE = "PERSISTENCE"
    COMPLETED = "COMPLETED"


class DeduplicationResult(StrEnum):
    """Результат дедупликации наблюдения против реестра активов.

    MATCHED — уверенное совпадение с существующим активом (score ≥ match-порога);
    наблюдение привязано к активу.
    NEW_ASSET — совпадений нет; создан новый актив.
    POSSIBLE_MATCH — вероятное совпадение (score между порогами); требует
    проверки оператором, авто-объединение запрещено.
    AMBIGUOUS — несколько равнозначных кандидатов; требует разрешения
    оператором, авто-объединение запрещено.
    """

    MATCHED = "MATCHED"
    NEW_ASSET = "NEW_ASSET"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    AMBIGUOUS = "AMBIGUOUS"


class ReviewDecision(StrEnum):
    """Решение оператора при проверке ML-предсказания (append-only review).

    CONFIRMED — предсказание подтверждено без изменений.
    REJECTED — предсказание отклонено (ложная детекция).
    CORRECTED — предсказание исправлено; обязательно хотя бы одно поле
    corrected_* (тип объекта, состояние, тип дефекта, severity).
    NEEDS_MORE_INFORMATION — данных недостаточно, требуется повторный осмотр.
    """

    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CORRECTED = "CORRECTED"
    NEEDS_MORE_INFORMATION = "NEEDS_MORE_INFORMATION"


class DefectStatus(StrEnum):
    """Статус дефекта; переходы ограничены доменной матрицей.

    OPEN — дефект обнаружен, не подтверждён (создан pipeline).
    CONFIRMED — подтверждён оператором или review.
    IN_PROGRESS — дефект в работе (передан на устранение).
    RESOLVED — устранён (resolved_at заполнен); допустим reopen → OPEN.
    REJECTED — ложный дефект; терминальный статус через API
    (возврат только через review workflow).
    Матрица: OPEN → CONFIRMED/IN_PROGRESS/RESOLVED/REJECTED;
    CONFIRMED → IN_PROGRESS/RESOLVED; IN_PROGRESS → CONFIRMED/RESOLVED;
    RESOLVED → OPEN; REJECTED → (нет).
    """

    OPEN = "OPEN"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class PriorityBand(StrEnum):
    """Полоса приоритета объекта (производная от current_priority 0–100).

    HIGH_PRIORITY — высокий приоритет (priority ≥ 70 по умолчанию).
    MEDIUM_PRIORITY — средний приоритет (40–70).
    LOW_PRIORITY — низкий приоритет (< 40).
    NEEDS_REVIEW — низкая уверенность ML или неразрешённая дедупликация;
    требуется проверка оператором до принятия решений.
    """

    HIGH_PRIORITY = "HIGH_PRIORITY"
    MEDIUM_PRIORITY = "MEDIUM_PRIORITY"
    LOW_PRIORITY = "LOW_PRIORITY"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class AnonymizationStatus(StrEnum):
    """Статус анонимизации медиафайла (privacy filter).

    NOT_APPLIED — анонимизация не применялась (noop-фильтр честно сообщает это).
    APPLIED — анонимизация реально выполнена.
    FAILED — попытка анонимизации завершилась ошибкой.
    SKIPPED — анонимизация пропущена по политике для данного файла.
    """

    NOT_APPLIED = "NOT_APPLIED"
    APPLIED = "APPLIED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class StorageObjectKind(StrEnum):
    """Вид объекта в хранилище (StoredFile).

    ORIGINAL — исходный загруженный файл.
    FRAME — извлечённый кадр видео.
    CROP — вырезанный фрагмент кадра вокруг детекции (bbox).
    ANONYMIZED — анонимизированная версия файла.
    EXPORT — файл выгрузки (CSV/XLSX).
    """

    ORIGINAL = "ORIGINAL"
    FRAME = "FRAME"
    CROP = "CROP"
    ANONYMIZED = "ANONYMIZED"
    EXPORT = "EXPORT"


class FrameQualityVerdict(StrEnum):
    """Вердикт quality gate для кадра.

    PASS — кадр пригоден для обработки (резкость/экспозиция/размер в норме).
    REJECT — кадр отбракован (размытие, засветка, слишком малый размер);
    кадр получает статус REJECTED с reject_reason.
    """

    PASS = "PASS"  # noqa: S105
    REJECT = "REJECT"


class AuditAction(StrEnum):
    """Действие в append-only журнале аудита.

    CREATE — создание сущности.
    UPDATE — изменение сущности.
    DELETE — удаление сущности.
    REVIEW — операторская проверка.
    LOGIN — вход пользователя.
    EXPORT — выгрузка данных.
    JOB_RETRY — повторный запуск job.
    JOB_CANCEL — отмена job.
    """

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    REVIEW = "REVIEW"
    LOGIN = "LOGIN"
    EXPORT = "EXPORT"
    JOB_RETRY = "JOB_RETRY"
    JOB_CANCEL = "JOB_CANCEL"


class ConditionChangeSource(StrEnum):
    """Источник изменения состояния объекта (asset_condition_history).

    ML_PREDICTION — изменение по предсказанию ML.
    HUMAN_REVIEW — изменение по решению оператора (review).
    MANUAL_EDIT — ручное изменение (PATCH asset).
    SYSTEM — системное изменение (пересчёт политик, миграции).
    """

    ML_PREDICTION = "ML_PREDICTION"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    MANUAL_EDIT = "MANUAL_EDIT"
    SYSTEM = "SYSTEM"


class FrameStatus(StrEnum):
    """Итоговый статус кадра в job_frames.

    PROCESSED — кадр успешно обработан (детекции сохранены).
    REJECTED — кадр отбракован quality gate (reject_reason).
    FAILED — ошибка обработки кадра (ML/storage; error_code); job не падает.
    SKIPPED — кадр пропущен (например, уже обработан при повторном запуске).
    """

    PROCESSED = "PROCESSED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ObservationReviewStatus(StrEnum):
    """Статус операторской проверки наблюдения.

    UNREVIEWED — не проверено (очередь review: review_status=UNREVIEWED).
    CONFIRMED — предсказание подтверждено.
    REJECTED — предсказание отклонено как ложное.
    CORRECTED — предсказание исправлено оператором (effective_* поля).
    NEEDS_MORE_INFORMATION — требуется дополнительная информация.
    """

    UNREVIEWED = "UNREVIEWED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CORRECTED = "CORRECTED"
    NEEDS_MORE_INFORMATION = "NEEDS_MORE_INFORMATION"


class TrainingExampleStatus(StrEnum):
    """Статус training example (подтверждённые/исправленные детекции для ML).

    PENDING — пример создан, ожидает выгрузки для дообучения.
    EXPORTED — пример выгружен во внешний ML-контур.
    """

    PENDING = "PENDING"
    EXPORTED = "EXPORTED"
