from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class AuthMode(StrEnum):
    AUTO = "auto"
    AZURE_CLI = "azure-cli"
    WAM = "wam"
    INTERACTIVE = "interactive"
    DEVICE_CODE = "device-code"


class AuthConfig(BaseModel):
    client_id: str
    tenant_id: str
    scopes: list[str]
    mode: AuthMode = AuthMode.AUTO
    cache_namespace: str = "mtg-microsoft-auth"
    allow_broker: bool = True
    request_retry_count: int = Field(default=4, ge=0, le=10)
    request_retry_base_seconds: int = Field(default=2, ge=1, le=60)

    @field_validator("client_id", "tenant_id")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        if value in {"common", "organizations", "consumers"}:
            return value
        parts = value.split("-")
        if len(parts) != 5 or not all(parts):
            raise ValueError(f"Invalid UUID format: {value}")
        return value

    def cache_path(self) -> Path:
        base = Path(os.environ.get("USERPROFILE") or Path.home())
        return base / ".config" / self.cache_namespace / "token_cache.bin"
