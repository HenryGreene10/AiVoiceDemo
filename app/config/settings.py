"""Tenant configuration helpers loaded from environment variables.

# TENANT_KEYS: comma-separated list, e.g. "demo-blog-01,client-foo,client-bar"
"""

from functools import lru_cache
import os
from pydantic import BaseModel, Field


TENANT_KEYS_ENV = "TENANT_KEYS"


class TenantSettings(BaseModel):
    tenant_keys: list[str] = Field(
        default_factory=list,
        description="Comma-separated tenant allowlist sourced from TENANT_KEYS.",
    )

    @classmethod
    def from_env(cls) -> "TenantSettings":
        raw = os.getenv(TENANT_KEYS_ENV, "")
        keys = [s.strip() for s in raw.split(",") if s.strip()]
        return cls(tenant_keys=keys)


@lru_cache(maxsize=1)
def get_tenant_settings() -> TenantSettings:
    """Return cached tenant settings so every import gets the same state."""
    return TenantSettings.from_env()
