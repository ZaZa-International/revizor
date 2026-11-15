"""All ORM models. Import this module before configuring mappers."""

from app.infrastructure.database.models.asset import Asset
from app.infrastructure.database.models.defect import Defect, defect_observations
from app.infrastructure.database.models.history import AssetConditionHistory
from app.infrastructure.database.models.idempotency import IdempotencyRecord
from app.infrastructure.database.models.job import JobFrame, ProcessingJob
from app.infrastructure.database.models.observation import Observation
from app.infrastructure.database.models.review import Review
from app.infrastructure.database.models.route import Route
from app.infrastructure.database.models.stored_file import StoredFile
from app.infrastructure.database.models.training import TrainingExample
from app.infrastructure.database.models.upload import Upload
from app.infrastructure.database.models.user import AuditLog, User

__all__ = [
    "Asset",
    "AssetConditionHistory",
    "AuditLog",
    "Defect",
    "IdempotencyRecord",
    "JobFrame",
    "Observation",
    "ProcessingJob",
    "Review",
    "Route",
    "StoredFile",
    "TrainingExample",
    "Upload",
    "User",
    "defect_observations",
]
