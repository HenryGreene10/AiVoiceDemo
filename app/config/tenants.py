import os
from datetime import date
from typing import Any, Dict

from app.config.settings import get_tenant_settings


def _default_max_renders() -> int:
    return int(os.getenv("TENANT_DEFAULT_MAX_RENDERS", "50"))


def _default_max_chars_per_article() -> int:
    """
    Approximate per-article text cap for trial tenants.
    ~20 minutes of audio at ~750 characters/minute ≈ 15,000 chars.
    This is a soft limit used to truncate over-long trial articles.
    """
    return int(os.getenv("TENANT_DEFAULT_MAX_CHARS_PER_ARTICLE", "15000"))


def _base_tenants() -> Dict[str, Dict[str, Any]]:
    return {
        "demo": {
            "max_renders_per_day": 50,
        },
        "trial": {
            "max_renders_per_day": 75,
            # Per-article soft cap for trial tenants (~20 minutes of audio).
            "max_chars_per_article": _default_max_chars_per_article(),
        },
        # Example of how we'll add paying customers later:
        # "customer-foo": {"max_renders_per_day": 200},
    }


def _build_tenant_config() -> Dict[str, Dict[str, Any]]:
    tenants = _base_tenants()
    settings = get_tenant_settings()
    default_limit = _default_max_renders()
    default_chars = _default_max_chars_per_article()
    for tenant_key in settings.tenant_keys:
        cfg = tenants.setdefault(
            tenant_key,
            {
                "max_renders_per_day": default_limit,
                # Env-driven tenants get the same per-article default unless overridden.
                "max_chars_per_article": default_chars,
            },
        )
        cfg.setdefault("max_renders_per_day", default_limit)
        cfg.setdefault("max_chars_per_article", default_chars)
    return tenants


# Hard coded tenant definitions until we plumb in a DB.
TENANTS: Dict[str, Dict[str, Any]] = _build_tenant_config()

# Simple in-memory usage tracker keyed by tenant.
TENANT_USAGE: Dict[str, Dict[str, Any]] = {}
