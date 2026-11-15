"""ML provider selection based on application settings."""

from __future__ import annotations

from app.application.interfaces.ml_provider import MLProvider
from app.config import Settings
from app.infrastructure.ml.http_provider import HTTPMLProvider
from app.infrastructure.ml.mock_provider import MockMLProvider


def build_ml_provider(settings: Settings) -> MLProvider:
    if settings.ml_provider == "http":
        return HTTPMLProvider(settings)
    return MockMLProvider()
