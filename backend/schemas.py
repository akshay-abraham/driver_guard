"""
schemas.py
==========
Pydantic models describing the JSON contracts between backend and frontend.
Keeping these explicit (rather than passing dicts around) gives us request
validation for free and documents the WebSocket protocol in one place.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ConfigUpdateRequest(BaseModel):
    """
    Partial update to the live threshold configuration. Any subset of
    Thresholds field names may be supplied; unknown keys are ignored.
    Sent either as a REST POST to /api/config or as a WebSocket message
    with type == "config_update".
    """
    values: Dict[str, Any] = Field(default_factory=dict)


class SessionControlRequest(BaseModel):
    action: str  # "reset"
