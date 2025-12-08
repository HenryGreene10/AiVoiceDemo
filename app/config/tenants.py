from datetime import date
from typing import Any, Dict

# Hard coded tenant definitions until we plumb in a DB.
TENANTS: Dict[str, Dict[str, Any]] = {
    "demo": {
        "max_renders_per_day": 50,
    },
    "trial": {
        "max_renders_per_day": 75,
    },
    # Example of how we'll add paying customers later:
    # "customer-foo": {"max_renders_per_day": 200},
}

# Simple in-memory usage tracker keyed by tenant.
TENANT_USAGE: Dict[str, Dict[str, Any]] = {}
