import os
import uuid
import math
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import Column, DateTime, Integer, String, create_engine
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


def create_tenant(session: Session, plan_tier: str) -> Tenant:
    plan = (plan_tier or "trial").lower()
    now = _utcnow()
    tenant = Tenant(
        tenant_key=str(uuid.uuid4()),
        plan_tier=plan,
        used_seconds_month=0,
        renewal_at=now + timedelta(days=30),
        created_at=now,
    )
    session.add(tenant)
    return tenant


def list_tenants(session: Session) -> list[Tenant]:
    return list(session.query(Tenant).all())
