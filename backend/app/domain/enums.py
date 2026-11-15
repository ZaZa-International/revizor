"""Domain enumerations shared across the system.

These are pure-Python enums with no dependency on FastAPI/SQLAlchemy/ML.
DB models map to these via SQLAlchemy Enum with native PostgreSQL types.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"
    SERVICE = "SERVICE"


class MediaType(StrEnum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"


class GeolocationStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    ESTIMATED = "ESTIMATED"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


class GeolocationSource(StrEnum):
    GPS = "GPS"
    MANUAL = "MANUAL"
    MAP_MATCHING = "MAP_MATCHING"
    VISUAL = "VISUAL"
    UNKNOWN = "UNKNOWN"


class LifecycleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    RETIRED = "RETIRED"
    UNKNOWN = "UNKNOWN"


class JobStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProcessingStage(StrEnum):
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
    MATCHED = "MATCHED"
    NEW_ASSET = "NEW_ASSET"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    AMBIGUOUS = "AMBIGUOUS"


class ReviewDecision(StrEnum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CORRECTED = "CORRECTED"
    NEEDS_MORE_INFORMATION = "NEEDS_MORE_INFORMATION"


class DefectStatus(StrEnum):
    OPEN = "OPEN"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class PriorityBand(StrEnum):
    HIGH_PRIORITY = "HIGH_PRIORITY"
    MEDIUM_PRIORITY = "MEDIUM_PRIORITY"
    LOW_PRIORITY = "LOW_PRIORITY"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class AnonymizationStatus(StrEnum):
    NOT_APPLIED = "NOT_APPLIED"
    APPLIED = "APPLIED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class StorageObjectKind(StrEnum):
    ORIGINAL = "ORIGINAL"
    FRAME = "FRAME"
    CROP = "CROP"
    ANONYMIZED = "ANONYMIZED"
    EXPORT = "EXPORT"


class FrameQualityVerdict(StrEnum):
    PASS = "PASS"  # noqa: S105
    REJECT = "REJECT"


class AuditAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    REVIEW = "REVIEW"
    LOGIN = "LOGIN"
    EXPORT = "EXPORT"
    JOB_RETRY = "JOB_RETRY"
    JOB_CANCEL = "JOB_CANCEL"


class ConditionChangeSource(StrEnum):
    ML_PREDICTION = "ML_PREDICTION"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    MANUAL_EDIT = "MANUAL_EDIT"
    SYSTEM = "SYSTEM"


class FrameStatus(StrEnum):
    PROCESSED = "PROCESSED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ObservationReviewStatus(StrEnum):
    UNREVIEWED = "UNREVIEWED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CORRECTED = "CORRECTED"
    NEEDS_MORE_INFORMATION = "NEEDS_MORE_INFORMATION"


class TrainingExampleStatus(StrEnum):
    PENDING = "PENDING"
    EXPORTED = "EXPORTED"
