"""SportAPI RapidAPI — fonte secondaria (admin/debug only)."""

from app.services.sportapi.sportapi_client import (
    SportApiClient,
    SportApiDisabledError,
    SportApiError,
)

__all__ = [
    "SportApiClient",
    "SportApiDisabledError",
    "SportApiError",
]
