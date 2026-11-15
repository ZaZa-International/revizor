from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    assets,
    auth,
    defects,
    exports,
    files,
    jobs,
    ml,
    observations,
    reviews,
    routes,
    uploads,
)
from app.api.v1 import (
    map as map_layer,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(uploads.router)
api_router.include_router(jobs.router)
api_router.include_router(assets.router)
api_router.include_router(observations.router)
api_router.include_router(defects.router)
api_router.include_router(reviews.router)
api_router.include_router(map_layer.router)
api_router.include_router(routes.router)
api_router.include_router(analytics.router)
api_router.include_router(exports.router)
api_router.include_router(ml.router)
api_router.include_router(files.router)
