import json
import os
import math
import secrets
from urllib.parse import urlparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import Column, DateTime, Integer, String, create_engine, text
from sqlalchemy import inspect
from sqlalchemy.orm import Session, declarative_base, sessionmaker


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize datetimes to aware UTC so comparisons never mix naive/aware."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# Store under /cache so Render's persistent disk keeps tenant keys/usage across deploys.
DEFAULT_SQLITE_PATH = Path("/cache/tenants.db")
DB_PATH = Path(os.getenv("TENANT_DB_PATH", DEFAULT_SQLITE_PATH))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    engine = create_engine(DATABASE_URL, future=True)
else:
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
        future=True,
    )

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)
Base = declarative_base()


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_key = Column(String, primary_key=True, index=True)
    plan_tier = Column(String, nullable=False)
    used_seconds_month = Column(Integer, nullable=False, default=0)
    renewal_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    allowed_domains = Column(String, nullable=True)
    status = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)

    @property
    def public_site_key(self) -> str:
        return self.tenant_key


TIER_QUOTAS_SECONDS = {
    "trial": 600,        # 10 min
    "creator": 7200,     # 2h
    "publisher": 36000,  # 10h
    "newsroom": 180000,  # 50h
}


def quota_for_plan(plan_tier: str) -> int:
    return TIER_QUOTAS_SECONDS.get((plan_tier or "").lower(), TIER_QUOTAS_SECONDS["trial"])


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def _ensure_columns() -> None:
    try:
        if engine.dialect.name == "sqlite":
            with engine.connect() as conn:
                rows = conn.execute(text("PRAGMA table_info(tenants)")).fetchall()
                existing = {row[1] for row in rows}
        else:
            existing = {col["name"] for col in inspect(engine).get_columns("tenants")}
    except Exception:
        return

    missing = {
        "allowed_domains": "TEXT",
        "status": "TEXT",
        "contact_email": "TEXT",
    }
    to_add = {name: sql_type for name, sql_type in missing.items() if name not in existing}
    if not to_add:
        return
    try:
        with engine.begin() as conn:
            for name, sql_type in to_add.items():
                conn.execute(text(f"ALTER TABLE tenants ADD COLUMN {name} {sql_type}"))
    except Exception:
        return


@contextmanager
def tenant_session() -> Iterable[Session]:
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_tenant(session: Session, tenant_key: str) -> Optional[Tenant]:
    if not tenant_key:
        return None
    return session.get(Tenant, tenant_key)


def refresh_renewal(session: Session, tenant: Tenant, now: Optional[datetime] = None) -> None:
    now = as_utc(now or _utcnow())
    renewal = as_utc(tenant.renewal_at)
    if renewal is None or now >= renewal:
        tenant.used_seconds_month = 0
        tenant.renewal_at = now + timedelta(days=30)


def record_usage_seconds(session: Session, tenant: Tenant, seconds: float) -> int:
    """Increment usage, returns new used_seconds_month."""
    refresh_renewal(session, tenant)
    inc = int(math.ceil(max(seconds or 0, 0)))
    tenant.used_seconds_month = int(tenant.used_seconds_month or 0) + inc
    return tenant.used_seconds_month


def _generate_public_site_key() -> str:
    return f"pk_live_{secrets.token_urlsafe(18)}"


def serialize_domains(domains: list[str] | None) -> str | None:
    if not domains:
        return None
    return json.dumps(domains, ensure_ascii=False)


def deserialize_domains(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
        if isinstance(data, str) and data.strip():
            return [data.strip()]
    except Exception:
        pass
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.lower() == "null":
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        parsed = urlparse(raw)
    except Exception:
        return None
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    return host or None


def normalize_domains(value: str | list[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        raw_items = [p.strip() for p in value.split(",") if p.strip()]
    else:
        raw_items = [str(p).strip() for p in value if str(p).strip()]
    normalized = []
    seen = set()
    for item in raw_items:
        host = normalize_domain(item)
        if not host or "*" in host or host in seen:
            continue
        seen.add(host)
        normalized.append(host)
    return normalized


def create_tenant(
    session: Session,
    plan_tier: str,
    public_site_key: str | None = None,
    allowed_domains: list[str] | None = None,
    status: str | None = "active",
    contact_email: str | None = None,
) -> Tenant:
    plan = (plan_tier or "trial").lower()
    now = _utcnow()
    tenant_key = public_site_key or _generate_public_site_key()
    tenant = Tenant(
        tenant_key=tenant_key,
        plan_tier=plan,
        used_seconds_month=0,
        renewal_at=now + timedelta(days=30),
        created_at=now,
        allowed_domains=serialize_domains(allowed_domains),
        status=status,
        contact_email=contact_email,
    )
    session.add(tenant)
    return tenant


def list_tenants(session: Session) -> list[Tenant]:
    return list(session.query(Tenant).all())
