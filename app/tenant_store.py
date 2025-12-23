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


def get_tenant_db_info() -> dict:
    if DATABASE_URL:
        url = engine.url
        driver = url.drivername or "database"
        host = url.host or ""
        name = url.database or ""
        if host or name:
            target = f"{driver}://{host}/{name}".rstrip("/")
        else:
            target = driver
        return {"target": target, "sqlite_path": None, "exists": None}
    return {
        "target": f"sqlite:///{DB_PATH}",
        "sqlite_path": str(DB_PATH),
        "exists": DB_PATH.exists(),
    }


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
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    stripe_checkout_session_id = Column(String, nullable=True)
    quota_seconds_month = Column(Integer, nullable=True)

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
        "stripe_customer_id": "TEXT",
        "stripe_subscription_id": "TEXT",
        "stripe_checkout_session_id": "TEXT",
        "quota_seconds_month": "INTEGER",
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


def get_tenant_by_stripe_customer_id(session: Session, stripe_customer_id: str) -> Optional[Tenant]:
    if not stripe_customer_id:
        return None
    return session.query(Tenant).filter(Tenant.stripe_customer_id == stripe_customer_id).first()


def get_tenant_by_stripe_subscription_id(session: Session, stripe_subscription_id: str) -> Optional[Tenant]:
    if not stripe_subscription_id:
        return None
    return session.query(Tenant).filter(Tenant.stripe_subscription_id == stripe_subscription_id).first()


def get_tenant_by_stripe_checkout_session_id(session: Session, stripe_checkout_session_id: str) -> Optional[Tenant]:
    if not stripe_checkout_session_id:
        return None
    return session.query(Tenant).filter(Tenant.stripe_checkout_session_id == stripe_checkout_session_id).first()


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
    items: list[str] = []
    try:
        data = json.loads(value)
        if isinstance(data, list):
            items = [str(x).strip() for x in data if str(x).strip()]
        if isinstance(data, str) and data.strip():
            items = [data.strip()]
    except Exception:
        items = [p.strip() for p in value.split(",") if p.strip()]
    normalized = []
    seen = set()
    for item in items:
        host = normalize_domain(item)
        if not host or "*" in host or host in seen:
            continue
        seen.add(host)
        normalized.append(host)
    return normalized


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
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    stripe_checkout_session_id: str | None = None,
    quota_seconds_month: int | None = None,
) -> Tenant:
    plan = (plan_tier or "trial").lower()
    now = _utcnow()
    tenant_key = public_site_key or _generate_public_site_key()
    normalized_domains = normalize_domains(allowed_domains)
    tenant = Tenant(
        tenant_key=tenant_key,
        plan_tier=plan,
        used_seconds_month=0,
        renewal_at=now + timedelta(days=30),
        created_at=now,
        allowed_domains=serialize_domains(normalized_domains),
        status=status,
        contact_email=contact_email,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        stripe_checkout_session_id=stripe_checkout_session_id,
        quota_seconds_month=quota_seconds_month,
    )
    session.add(tenant)
    return tenant


def upsert_tenant(
    session: Session,
    tenant_key: str,
    plan_tier: str | None = None,
    allowed_domains: list[str] | str | None = None,
    status: str | None = None,
    contact_email: str | None = None,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    stripe_checkout_session_id: str | None = None,
    quota_seconds_month: int | None = None,
    created_at: datetime | None = None,
    renewal_at: datetime | None = None,
) -> Tenant:
    tenant = session.get(Tenant, tenant_key)
    now = _utcnow()
    normalized_domains = normalize_domains(allowed_domains)
    if tenant is None:
        tenant = Tenant(
            tenant_key=tenant_key,
            plan_tier=(plan_tier or "trial").lower(),
            used_seconds_month=0,
            renewal_at=renewal_at or now + timedelta(days=30),
            created_at=created_at or now,
            allowed_domains=serialize_domains(normalized_domains),
            status=status or "active",
            contact_email=contact_email,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_checkout_session_id=stripe_checkout_session_id,
            quota_seconds_month=quota_seconds_month,
        )
        session.add(tenant)
        return tenant

    if plan_tier:
        tenant.plan_tier = (plan_tier or tenant.plan_tier or "trial").lower()
    if status is not None:
        tenant.status = status
    if contact_email:
        tenant.contact_email = contact_email
    if stripe_customer_id:
        tenant.stripe_customer_id = stripe_customer_id
    if stripe_subscription_id:
        tenant.stripe_subscription_id = stripe_subscription_id
    if stripe_checkout_session_id:
        tenant.stripe_checkout_session_id = stripe_checkout_session_id
    if quota_seconds_month is not None:
        tenant.quota_seconds_month = quota_seconds_month
    if allowed_domains is not None:
        tenant.allowed_domains = serialize_domains(normalized_domains)
    if created_at and not tenant.created_at:
        tenant.created_at = created_at
    if renewal_at:
        tenant.renewal_at = renewal_at
    return tenant


def list_tenants(session: Session) -> list[Tenant]:
    return list(session.query(Tenant).all())
