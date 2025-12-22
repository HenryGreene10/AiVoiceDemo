# main.py
import logging
import io
import math
import os, hashlib, requests, time, httpx
import secrets
from pathlib import Path
from collections import OrderedDict
from dotenv import load_dotenv; 
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import Response, StreamingResponse, JSONResponse, FileResponse, PlainTextResponse, HTMLResponse
from typing import Optional, Any, Dict
from dataclasses import dataclass
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi import Query, Body
import trafilatura, re, requests as http, json
from html import escape
from trafilatura.metadata import extract_metadata
from typing import Tuple
from urllib.parse import urlparse, quote
import socket, ipaddress, asyncio, json
import re
from fastapi.staticfiles import StaticFiles
import csv
from threading import Lock
from datetime import datetime, timezone, date, timedelta
from mutagen.mp3 import MP3
import stripe
from app.config.tenants import TENANTS, TENANT_USAGE
from app.tenant_store import (
    Tenant,
    create_tenant,
    deserialize_domains,
    get_tenant,
    init_db as init_tenant_db,
    list_tenants,
    normalize_domains,
    quota_for_plan,
    record_usage_seconds,
    refresh_renewal,
    tenant_session,
    TIER_QUOTAS_SECONDS,
)
from fastapi.exception_handlers import http_exception_handler as fastapi_http_exception_handler

logger = logging.getLogger("easyaudio")

CACHE_ROOT = Path(os.getenv("CACHE_ROOT", "/cache")).resolve()
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
logger.info(f"[cache] CACHE_ROOT={CACHE_ROOT}")

# Tenant keys:
# - data-ail-tenant is a public site key sent as x-tenant-key from the widget.
# - Tenant existence, quotas, and domain allowlist live in the DB (TENANT_KEYS is deprecated).
# - All TTS/cache endpoints call get_validated_tenant() so every request maps to a tenant.

def _redact_key(value: str | None) -> str:
    if not value:
        return "missing"
    raw = value.strip()
    if len(raw) <= 10:
        return f"{raw[:2]}...{raw[-2:]}"
    return f"{raw[:6]}...{raw[-4:]}"


def _tenant_from_body(body: object) -> str | None:
    if body is None:
        return None
    data = None
    try:
        if isinstance(body, BaseModel):
            # Prefer model_dump for pydantic v2 but fall back cleanly.
            data = body.model_dump(exclude_none=True) if hasattr(body, "model_dump") else body.dict()
        elif isinstance(body, dict):
            data = body
        elif hasattr(body, "dict"):
            data = body.dict()
    except Exception:
        data = None
    if not isinstance(data, dict):
        return None
    for key in ("tenant", "tenant_key", "tenantKey"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _extract_tenant_key(request: Request, body: object | None = None) -> str | None:
    header = request.headers.get("x-tenant-key")
    if header and header.strip():
        return header.strip()
    body_val = _tenant_from_body(body)
    if body_val:
        return body_val
    tenant_param = request.query_params.get("tenant")
    if tenant_param and tenant_param.strip():
        return tenant_param.strip()
    return None


def get_request_domain(request: Request) -> str | None:
    origin = request.headers.get("origin") or ""
    referer = request.headers.get("referer") or ""
    candidate = origin.strip() or referer.strip()
    if not candidate or candidate.lower() == "null":
        return None
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    try:
        parsed = urlparse(candidate)
    except Exception:
        return None
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    return host or None


def is_domain_allowed(domain: str, allowed_domains: list[str]) -> bool:
    if not domain:
        return False
    return domain in allowed_domains


def _get_allowed_domains(tenant: Tenant) -> list[str]:
    return normalize_domains(deserialize_domains(getattr(tenant, "allowed_domains", None)))


def _tenant_error(message: str, code: str = "invalid_tenant") -> None:
    raise HTTPException(status_code=401, detail={"error": code, "message": message})


def _load_tenant_record(tenant_id: str) -> Tenant:
    with tenant_session() as session:
        tenant = get_tenant(session, tenant_id)
        if not tenant:
            _tenant_error("Unknown tenant key.", code="invalid_tenant")
        refresh_renewal(session, tenant)
        return tenant


def get_validated_tenant(request: Request, body: object | None = None) -> str:
    """Resolve tenant from request metadata and enforce DB-backed tenant existence."""
    tenant_id = _extract_tenant_key(request, body=body)
    if not tenant_id:
        logger.warning("[tenant] Missing tenant key")
        _tenant_error("Missing tenant key (x-tenant-key header, body.tenant, or tenant query param).", code="missing_tenant_key")

    # Persistent tenant store is the source of truth for quotas and existence.
    _load_tenant_record(tenant_id)

    return tenant_id


def get_validated_tenant_record(
    request: Request,
    body: object | None = None,
) -> tuple[str, Tenant]:
    tenant_id = _extract_tenant_key(request, body=body)
    if not tenant_id:
        logger.warning("[tenant] Missing tenant key")
        _tenant_error(
            "Missing tenant key (x-tenant-key header, body.tenant, or tenant query param).",
            code="missing_tenant_key",
        )
    tenant = _load_tenant_record(tenant_id)
    return tenant_id, tenant


def enforce_domain_allowlist(request: Request, tenant: Tenant, tenant_key: str) -> None:
    domain = get_request_domain(request)
    if not domain:
        if DEMO_MODE:
            logger.warning("[tenant] Missing origin/referer (demo allow) key=%s", _redact_key(tenant_key))
            return
        raise HTTPException(
            status_code=403,
            detail={"error": "domain_required", "message": "Origin/Referer required"},
        )

    allowed = _get_allowed_domains(tenant)
    if not allowed or not is_domain_allowed(domain, allowed):
        raise HTTPException(
            status_code=403,
            detail={"error": "domain_not_allowed", "message": "Domain not allowed for this key"},
        )


def get_tenant_limits(tenant_id: str) -> Dict[str, Any]:
    """
    Return simple limit information for a tenant.
    Currently used for per-article text caps on trial tenants.
    """
    cfg = TENANTS.get(tenant_id, {})
    return {
        "max_renders_per_day": cfg.get("max_renders_per_day"),
        "max_chars_per_article": cfg.get("max_chars_per_article"),
    }


def enforce_article_length_limit(tenant_id: str, text: str) -> tuple[str, bool]:
    """
    Apply a per-article character limit for tenants that define max_chars_per_article.

    Returns:
      (possibly_truncated_text, was_truncated_flag)

    For trial tenants, this enforces a soft ~20 minute cap so a single long
    article can't burn a huge amount of ElevenLabs minutes during the trial.
    """
    limits = get_tenant_limits(tenant_id)
    max_chars = limits.get("max_chars_per_article")
    if not max_chars or max_chars <= 0:
        # No limit configured for this tenant.
        return text, False

    length = len(text or "")
    if length <= max_chars:
        return text, False

    truncated = (text or "")[:max_chars]

    logger.info(
        "[quota] tenant=%s exceeded max_chars_per_article (%s > %s); truncating text for trial preview",
        tenant_id,
        length,
        max_chars,
    )

    return truncated, True


def _quota_error_payload(plan: str, quota: int, used: int) -> dict[str, object]:
    plan_name = (plan or "trial")
    return {
        "error": "quota_exceeded",
        "message": f"Monthly quota reached for the {plan_name} plan.",
        "plan": plan_name,
        "limit_seconds": int(quota),
        "used_seconds": int(used),
    }


def ensure_tenant_quota_ok(tenant_id: str, request: Request | None = None) -> dict[str, object]:
    """
    Refresh renewal window and enforce monthly quota for a tenant.
    Returns a small dict with quota state for logging.
    """
    with tenant_session() as session:
        tenant = get_tenant(session, tenant_id)
        if not tenant:
            _tenant_error("Unknown tenant key.", code="invalid_tenant")
        refresh_renewal(session, tenant)
        quota = quota_for_plan(tenant.plan_tier)
        if tenant.used_seconds_month >= quota:
            payload = _quota_error_payload(tenant.plan_tier, quota, tenant.used_seconds_month)
            try:
                _maybe_send_quota_email(tenant, quota, request=request)
            except Exception as e:
                logger.warning("[quota] notify error: %s", e)
            raise HTTPException(status_code=402, detail=payload)
        return {
            "plan": tenant.plan_tier,
            "quota": quota,
            "used": tenant.used_seconds_month,
            "renewal_at": tenant.renewal_at,
        }


def record_tenant_usage_seconds(tenant_id: str, seconds: float) -> int | None:
    if seconds is None:
        return None
    with tenant_session() as session:
        tenant = get_tenant(session, tenant_id)
        if not tenant:
            logger.warning("[tenant] usage skip; missing tenant=%s", tenant_id)
            return None
        return record_usage_seconds(session, tenant, seconds)


def mp3_duration_seconds(path: Path) -> int:
    try:
        audio = MP3(path)
        dur = getattr(audio, "info", None).length if hasattr(audio, "info") else None
        return int(math.ceil(float(dur))) if dur else 0
    except Exception as e:
        logger.warning("[tenant] unable to read mp3 duration for %s: %s", path, e)
        return 0


def estimate_seconds_from_text(text: str) -> int:
    cleaned = (text or "").strip()
    if not cleaned:
        return 0
    return max(5, int(round(len(cleaned) / 15.0)))

# --- rate limiting ---
import time, collections

RATE_LIMITS = {
    "per_ip":   (60, 60),   # 60 requests / 60s
    "per_tenant": (300, 60) # 300 requests / 60s
}
_ip_hits = collections.defaultdict(list)      # ip -> [timestamps]
_tenant_hits = collections.defaultdict(list)  # tenant -> [timestamps]

def _allow(counter: dict, key: str, limit: int, window_s: int) -> bool:
    now = time.time()
    arr = counter[key]
    # drop old
    while arr and now - arr[0] > window_s:
        arr.pop(0)
    if len(arr) >= limit:
        return False
    arr.append(now)
    return True

def _client_ip(request: Request) -> str:
    xf = request.headers.get("x-forwarded-for")
    return (xf.split(",")[0].strip() if xf else request.client.host) or "unknown"

def rate_limit_check(request: Request, body: object | None = None):
    ip = _client_ip(request)
    ok_ip = _allow(_ip_hits, ip, *RATE_LIMITS["per_ip"])
    # tenant key (or 'public' if open mode)
    tenant = _extract_tenant_key(request, body=body) or "public"
    ok_tenant = _allow(_tenant_hits, tenant, *RATE_LIMITS["per_tenant"])
    if not (ok_ip and ok_tenant):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please retry later.")


def check_and_increment_quota(tenant_id: str) -> None:
    """Compatibility shim: use the persistent quota store."""
    ensure_tenant_quota_ok(tenant_id)
#from src.metrics import write_stream_row
#try:
#    from src.prosody import prepare_article
#except Exception:
#    from src.prosody import prepare_article



# --- metrics setup ---
METRICS_DIR = Path("metrics"); METRICS_DIR.mkdir(exist_ok=True)
METRICS_FILE = METRICS_DIR / "streams.csv"

def write_stream_row(ts_ms: int, cache: str, ttfb_ms: int, bytes_total: int, model: str, key_hash: str):
    is_new = not METRICS_FILE.exists()
    with METRICS_FILE.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["ts_ms","cache","ttfb_ms","bytes","model","hash"])
        w.writerow([ts_ms, cache, ttfb_ms, bytes_total, model, key_hash])

# --- config / env
load_dotenv(".env")
from dotenv import load_dotenv; load_dotenv()
API_KEY  = (os.getenv("ELEVENLABS_API_KEY","").strip())
VOICE_ID = (os.getenv("VOICE_ID","").strip())
MODEL_ID = (os.getenv("MODEL_ID","eleven_turbo_v2").strip())
CACHE_DIR = CACHE_ROOT
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes")
MAX_CHARS = 160000  # ~90 seconds
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "").strip()
STUB_TTS = os.getenv("STUB_TTS", "0").strip().lower() in ("1","true","yes")
OPT_LATENCY = int(os.getenv("OPT_LATENCY", "0").strip())  # was 2; 0 = safest with ElevenLabs
TENANT_ALLOWLIST_ENFORCE = os.getenv("TENANT_ALLOWLIST_ENFORCE", "0").strip().lower() in ("1","true","yes")
# Deprecated: TENANT_KEYS/TENANT_ALLOWLIST_ENFORCE no longer gate tenant auth.
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip()
PUBLIC_API_BASE = os.getenv("PUBLIC_API_BASE", "").strip()
PUBLIC_WIDGET_URL = os.getenv("PUBLIC_WIDGET_URL", "").strip()
PRICE_CREATOR_ID = os.getenv("PRICE_CREATOR_ID", "").strip()
PRICE_PUBLISHER_ID = os.getenv("PRICE_PUBLISHER_ID", "").strip()
PRICE_NEWSROOM_ID = os.getenv("PRICE_NEWSROOM_ID", "").strip()
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

@dataclass
class TenantConfig:
    voice_id: str
    model_id: str | None = None

DEFAULT_TENANT_VOICE = (VOICE_ID or os.getenv("ELEVENLABS_VOICE", "").strip() or "21m00Tcm4TlvDq8ikWAM")
VOICE_TENANTS: dict[str, TenantConfig] = {
    "default": TenantConfig(voice_id=DEFAULT_TENANT_VOICE),
    "demo-blog": TenantConfig(
        voice_id=os.getenv("DEMO_BLOG_VOICE", DEFAULT_TENANT_VOICE)
    ),
}


# --- app
app = FastAPI()

@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code in (401, 402) and isinstance(exc.detail, dict) and exc.detail.get("error"):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return await fastapi_http_exception_handler(request, exc)

# --- Include wrap router
from server.wrap import router as wrap_router
app.include_router(wrap_router)

# --- Helper that returns bytes for a chunk (no generator) ---
async def tts_bytes(
    text: str,
    voice_id: str,
    model_id: str,
    voice_settings: dict | None = None,
) -> bytes:
    client: httpx.AsyncClient = app.state.http_client
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": voice_settings or {
            "stability": 0.45,
            "similarity_boost": 0.85,
            "style": 0.60,
            "use_speaker_boost": True,
        },
        "optimize_streaming_latency": 2,
    }
    headers = {
        "xi-api-key": API_KEY,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }

    stream_url    = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    nonstream_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    # --- stream attempt
    try:
        resp = await client.post(stream_url, headers=headers, json=payload, timeout=60.0)
    except Exception as e:
        print({"event": "tts_conn_fail", "err": str(e)[:300]})
        raise HTTPException(status_code=502, detail=f"TTS upstream connection failed: {e}")

    if resp.status_code == 200 and resp.content:
        return resp.content

    body1 = (resp.text or "")[:500]
    print({"event": "tts_upstream_err", "status": resp.status_code, "body": body1})

    # --- non-stream fallback
    resp2 = await client.post(nonstream_url, headers=headers, json=payload, timeout=60.0)
    if resp2.status_code == 200 and resp2.content:
        print({"event": "tts_nonstream_ok"})
        return resp2.content

    body2 = (resp2.text or "")[:500]
    print({"event": "tts_nonstream_err", "status": resp2.status_code, "body": body2})

    # Bubble the upstream reason
    raise HTTPException(
        status_code=resp2.status_code if resp2.status_code != 200 else 502,
        detail=f"TTS error. stream {resp.status_code}: {body1}; nonstream {resp2.status_code}: {body2}",
    )

# --- Simple, robust sentence chunker ---
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

def chunk_by_sentence(s: str, target: int = 1200, hard_max: int = 1600) -> list[str]:
    parts, cur, total = [], [], 0
    for sent in re.split(SENTENCE_SPLIT, s):
        sent = (sent or "").strip()
        if not sent:
            continue
        if total + len(sent) > target and cur:
            parts.append(" ".join(cur)); cur, total = [], 0
        cur.append(sent); total += len(sent)
        if total > hard_max:
            parts.append(" ".join(cur)); cur, total = [], 0
    if cur:
        parts.append(" ".join(cur))
    return parts

@app.get("/read_chunked")
async def read_chunked(request: Request, url: str, voice: str | None = None, model: str | None = None):
    tenant_id = get_validated_tenant(request)
    ensure_tenant_quota_ok(tenant_id, request=request)
    # 1) Extract & prepare
    title, author, text = extract_article(url)
    cleaned = preprocess_for_tts(text or "")
    narration = prepare_article(title, author, cleaned)

    if not narration or len(narration.strip()) < 40:
        raise HTTPException(status_code=422, detail="No narratable text extracted from page")

    parts = chunk_by_sentence(narration, target=900, hard_max=1300)
    if not parts:
        raise HTTPException(status_code=422, detail="No narratable chunks produced")

    v = voice or VOICE_ID
    m = model or MODEL_ID
    usage_seconds = estimate_seconds_from_text(narration)

    # 2) PREFETCH FIRST CHUNK to avoid 200/0B
    try:
        first_text = enhance_prosody(preprocess_for_tts(parts[0]))
        first_bytes = await tts_bytes(first_text, v, m)
        if usage_seconds:
            record_tenant_usage_seconds(tenant_id, usage_seconds)
        print({"event": "chunk_ok", "i": 0, "bytes": len(first_bytes)})
    except Exception as e:
        # Fail BEFORE starting the stream
        raise HTTPException(status_code=502, detail=f"First chunk failed: {e}")

    # 3) Stream: yield first prefetch, then fetch the rest one by one
    async def multi():
        # first chunk we already have
        yield first_bytes
        for i, part in enumerate(parts[1:], start=1):
            try:
                part_text = enhance_prosody(preprocess_for_tts(part))
                data = await tts_bytes(part_text, v, m)
                print({"event": "chunk_ok", "i": i, "bytes": len(data)})
                yield data
            except Exception as e:
                print({"event": "chunk_fail", "i": i, "err": str(e)[:300]})
                break  # stop cleanly; do NOT raise once streaming has begun

    return StreamingResponse(multi(), media_type="audio/mpeg")


from fastapi.middleware.cors import CORSMiddleware
ALLOW_ORIGINS = os.getenv("ALLOW_ORIGINS","").strip()
ALLOWED = [o.strip() for o in ALLOW_ORIGINS.split(",") if o.strip()]
if not ALLOWED:
    ALLOWED = [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://hgtts.onrender.com",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

@app.get("/health")
def health():
    return {"ok": True}

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/cache", StaticFiles(directory=str(CACHE_DIR)), name="cache")

# --- simple preprocess to improve pauses & flow for TTS
def preprocess_for_tts(text: str) -> str:
    """Cleanup to remove citations, IPA/pronunciation, and tidy spacing."""
    t = text.replace("\r", "\n")

    # Wikipedia-style citations like [1], and editorial tags
    t = re.sub(r"\[\d+\]", "", t)
    t = re.sub(r"\[(?:citation|clarification|verification)\s+needed\]", "", t, flags=re.I)

    # Parenthetical pronunciation/IPA/listen asides e.g. (/ˈkæri/), (IPA: ...), (listen)
    t = re.sub(r"\s*\((?:IPA[:\s]|pronunciation[:\s]|listen\b|/)[^)]*\)\s*", " ", t, flags=re.I)

    # Strip non-story sections if present
    t = re.split(r"\n(?:References|External links|See also)\n", t, maxsplit=1)[0]

    # Bullets/newlines → sentences
    t = re.sub(r"\n\s*[-•*]\s+", ". ", t)
    t = re.sub(r"\n{2,}", ". ", t)
    t = re.sub(r"(?<![.!?])\n(?!\n)", ". ", t)

    # Spaces/punctuation tidy
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"([,.;:!?])(?=\S)", r"\1 ", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()

def enhance_prosody(raw: Optional[str]) -> str:
    """Lightly adjust whitespace and add gentle pauses for smoother narration."""
    if not raw:
        return ""

    cleaned = raw.replace("\r", " ")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    sentences = [s.strip() for s in parts if s.strip()]
    if not sentences:
        return cleaned

    with_paragraphs: list[str] = []
    for idx, s in enumerate(sentences):
        with_paragraphs.append(s)
        if (idx + 1) % 3 == 0 and idx != len(sentences) - 1:
            with_paragraphs.append("")

    return "\n".join(with_paragraphs)

# --- Robust fetch for /read
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
BASE_HDRS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

def normalize_url(u: str) -> str:
    u = u.strip()
    if not re.match(r"^https?://", u, flags=re.I):
        u = "https://" + u
    return u

def fetch_url(url: str, retries: int = 2, timeout: int = 15) -> str:
    last_err = None
    url = normalize_url(url)
    hdrs = dict(BASE_HDRS)
    hdrs["Referer"] = url
    for i in range(retries + 1):
        try:
            r = http.get(url, headers=hdrs, timeout=timeout, allow_redirects=True)
            if r.status_code in (403, 406) and "text/html" not in r.headers.get("Content-Type",""):
                hdrs2 = dict(hdrs); hdrs2["Accept"] = "text/html,*/*;q=0.5"
                r = http.get(url, headers=hdrs2, timeout=timeout, allow_redirects=True)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            time.sleep(0.6 * (i + 1))
    raise HTTPException(status_code=502, detail=f"Fetch failed: {last_err}")

# --- extract article cleanly (title, author, text)
def extract_article(url: str) -> Tuple[str, str, str]:
    """Return (title, author, text) using trafilatura with safe fallbacks."""
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise HTTPException(400, detail="Unable to fetch URL")

    # Body text: prefer plain text (more reliable than output='json')
    text = trafilatura.extract(
        downloaded,
        output="txt",
        include_comments=False,
        include_tables=False,
        include_links=False,
    ) or ""

    # Metadata: be tolerant to missing/varied shapes
    title = ""; author = ""
    try:
        md = extract_metadata(downloaded)
        if md:
            title = (getattr(md, "title", "") or "").strip()
            a = getattr(md, "author", None) or getattr(md, "authors", None)
            if isinstance(a, (list, tuple)):
                author = ", ".join([x for x in a if x]).strip()
            else:
                author = (a or "").strip()
    except Exception:
        pass

    return title, author, text

# keep a single async HTTP client alive for connection reuse (lower TTFB)
@app.on_event("startup")
async def _startup():
    app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    app.state.locks = {}
    init_tenant_db()
    
from fastapi.routing import APIRoute

@app.on_event("startup")
async def _list_routes():
    routes = []
    for r in app.router.routes:
        if isinstance(r, APIRoute):
            routes.append((r.path, sorted(list(r.methods))))
    print({"routes": routes})

@app.on_event("shutdown")
async def _shutdown():
    await app.state.http_client.aclose()

# --- simple PNA preflight helper (FastAPI's CORS doesn't add this header yet)
@app.options("/{path:path}")
async def preflight(req: Request, path: str):
    headers = {
        "Access-Control-Allow-Origin": req.headers.get("origin", "*") if ALLOWED else "*",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Private-Network": "true",
    }
    return Response(status_code=204, headers=headers)

# --- chunk by sentence
def chunk_by_sentence(s: str, target: int = 1200, hard_max: int = 1600) -> list[str]:
    parts, cur, total = [], [], 0
    for sent in re.split(r"(?<=[.!?])\s+", s):
        if not sent:
            continue
        if total + len(sent) > target and cur:
            parts.append(" ".join(cur)); cur, total = [], 0
        cur.append(sent); total += len(sent)
        if total > hard_max:
            parts.append(" ".join(cur)); cur, total = [], 0
    if cur:
        parts.append(" ".join(cur))
    return parts

@app.get("/read_chunked")
async def read_chunked(request: Request, url: str, voice: str | None = None, model: str | None = None):
    tenant_id = get_validated_tenant(request)
    ensure_tenant_quota_ok(tenant_id, request=request)
    title, author, text = extract_article(url)
    narration = prepare_article(title, author, preprocess_for_tts(text))
    parts = chunk_by_sentence(narration, target=1200, hard_max=1600)
    usage_seconds = estimate_seconds_from_text(narration)
    usage_recorded = False

    async def multi():
        nonlocal usage_recorded
        for i, part in enumerate(parts):
            try:
                async for b in stream_bytes_for_text_safe(
                    part, voice or VOICE_ID, model or MODEL_ID
                ):
                    if b:
                        if usage_seconds and not usage_recorded:
                            record_tenant_usage_seconds(tenant_id, usage_seconds)
                            usage_recorded = True
                        yield b
            except Exception as e:
                # Log, then stop or continue; do NOT raise after streaming started
                print({"event": "chunk_fail", "i": i, "err": str(e)[:200]})
                break  # or `continue` to try next part

    return StreamingResponse(multi(), media_type="audio/mpeg", headers={"X-AIL-Tenant": tenant_id})






# --- metrics API (admin)
@app.get("/admin/metrics.json")
async def metrics_json(n: int = Query(200, ge=1, le=5000), token: str = Query("")):
    if ADMIN_TOKEN and token != ADMIN_TOKEN:
        raise HTTPException(403, "Forbidden")
    file_path = Path("metrics/streams.csv")
    if not file_path.exists():
        return {"rows": []}
    try:
        import csv
        rows = []
        with file_path.open("r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                rows.append(row)
        rows = rows[-n:]
        return {"rows": rows}
    except Exception as e:
        raise HTTPException(500, f"metrics read error: {e}")

# --- analytics tracking (JSONL, internal-only) ---
ANALYTICS_JSONL = (CACHE_ROOT / "analytics.jsonl").resolve()
ANALYTICS_EVENTS = {"click_listen", "play_complete", "cache_hit", "cache_miss"}
_analytics_lock = Lock()


class AnalyticsEvent(BaseModel):
    event: str
    tenant: Optional[str] = None
    tenant_key: Optional[str] = None
    page_url: Optional[str] = None
    referrer: Optional[str] = None
    ts: Optional[int] = None


def _valid_admin_token(token: str) -> bool:
    expected = ADMIN_TOKEN or ADMIN_SECRET
    if not expected:
        return False
    return token == expected


def _require_admin_token(token: str) -> None:
    if not token or not _valid_admin_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _resolve_valid_tenant(request: Request, body: object | None = None) -> str | None:
    tenant_id = _extract_tenant_key(request, body=body)
    if not tenant_id:
        return None
    try:
        _load_tenant_record(tenant_id)
    except Exception:
        return None
    return tenant_id


def _append_analytics_event(
    event: str,
    tenant: str,
    page_url: str = "",
    referrer: str = "",
    ts_ms: int | None = None,
) -> None:
    ev = (event or "").strip().lower()
    if not tenant or ev not in ANALYTICS_EVENTS:
        return
    record = {
        "ts": int(ts_ms if ts_ms is not None else time.time() * 1000),
        "event": ev,
        "tenant": tenant,
        "page_url": page_url or "",
        "referrer": referrer or "",
    }
    try:
        with _analytics_lock:
            with ANALYTICS_JSONL.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False))
                f.write("\n")
    except Exception as e:
        logger.warning("analytics write failed: %s", e)


@app.post("/metric")
def metric(req: AnalyticsEvent, request: Request):
    tenant_id, tenant = get_validated_tenant_record(request, body=req)
    enforce_domain_allowlist(request, tenant, tenant_id)
    ev = (req.event or "").strip().lower()
    if not tenant_id or ev not in ANALYTICS_EVENTS:
        return Response(status_code=204)
    page_url = req.page_url or request.query_params.get("url") or request.headers.get("referer", "") or ""
    referrer = req.referrer or request.headers.get("referer", "") or ""
    ts_ms = req.ts if req.ts else None
    _append_analytics_event(ev, tenant_id, page_url=page_url, referrer=referrer, ts_ms=ts_ms)
    return {"ok": True}


def _iter_analytics(since_ts: int, tenant: str | None):
    if not ANALYTICS_JSONL.exists():
        return
    with ANALYTICS_JSONL.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            try:
                ts = int(obj.get("ts") or 0)
            except Exception:
                ts = 0
            if since_ts and ts < since_ts:
                continue
            tenant_val = obj.get("tenant") or ""
            if tenant and tenant_val != tenant:
                continue
            ev = (obj.get("event") or "").strip().lower()
            if ev not in ANALYTICS_EVENTS:
                continue
            yield {
                "ts": ts,
                "event": ev,
                "tenant": tenant_val,
                "page_url": obj.get("page_url") or "",
                "referrer": obj.get("referrer") or "",
            }


@app.get("/admin/analytics_summary.json")
def analytics_summary_admin(
    token: str = Query(...),
    days: int = Query(7, ge=1, le=90),
    tenant: Optional[str] = Query(None),
):
    _require_admin_token(token)
    now_ms = int(time.time() * 1000)
    since_ts = now_ms - int(days * 86400 * 1000)
    totals = {ev: 0 for ev in ANALYTICS_EVENTS}
    by_tenant: dict[str, dict[str, int]] = {}
    for rec in _iter_analytics(since_ts, tenant):
        ev = rec["event"]
        tenant_val = rec["tenant"] or ""
        totals[ev] = totals.get(ev, 0) + 1
        if tenant_val:
            bucket = by_tenant.setdefault(tenant_val, {k: 0 for k in ANALYTICS_EVENTS})
            bucket[ev] = bucket.get(ev, 0) + 1
    return {
        "range_days": days,
        "since_ts": since_ts,
        "totals": totals,
        "by_tenant": by_tenant,
    }


@app.get("/admin/analytics.csv")
def analytics_csv_admin(
    token: str = Query(...),
    days: int = Query(7, ge=1, le=90),
    tenant: Optional[str] = Query(None),
):
    _require_admin_token(token)
    now_ms = int(time.time() * 1000)
    since_ts = now_ms - int(days * 86400 * 1000)
    counts: dict[tuple[str, str, str], int] = {}
    for rec in _iter_analytics(since_ts, tenant):
        try:
            date_key = datetime.fromtimestamp(rec["ts"] / 1000, timezone.utc).date().isoformat()
        except Exception:
            continue
        key = (date_key, rec["tenant"] or "", rec["event"])
        counts[key] = counts.get(key, 0) + 1
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "tenant", "event", "count"])
    for (date_key, tnt, ev), count in sorted(counts.items()):
        writer.writerow([date_key, tnt, ev, count])
    return Response(content=output.getvalue(), media_type="text/csv")


class TenantCreateRequest(BaseModel):
    plan_tier: str | None = None
    domains: list[str] | str | None = None
    contact_email: str | None = None
    status: str | None = None


@app.post("/admin/tenants", response_model=None)
def create_tenant_admin(
    body: TenantCreateRequest,
    x_admin_secret: str | None = Header(default=None),
    request: Request,
):
    """Provision a tenant key with plan + quota. Protected by ADMIN_SECRET."""
    if not ADMIN_SECRET or x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    plan = (body.plan_tier or "trial").lower()
    if plan not in TIER_QUOTAS_SECONDS:
        raise HTTPException(
            status_code=400,
            detail="plan_tier must be one of: trial, creator, publisher, newsroom",
        )

    domains = normalize_domains(body.domains)
    if not domains:
        raise HTTPException(status_code=400, detail="domains is required (exact domain list)")

    status = (body.status or "active").strip().lower()

    with tenant_session() as session:
        tenant = create_tenant(
            session,
            plan,
            allowed_domains=domains,
            status=status,
            contact_email=body.contact_email,
        )
        quota_seconds = quota_for_plan(plan)
        public_base = _public_base_from_request(request)
        widget_src = _widget_src_url(public_base)
        embed_snippet = (
            "<script\n"
            f'  src="{widget_src}"\n'
            f'  data-ail-api-base="{public_base}"\n'
            f'  data-ail-tenant="{tenant.tenant_key}">\n'
            "</script>"
        )
        response = {
            "public_site_key": tenant.tenant_key,
            "plan_tier": tenant.plan_tier,
            "quota_seconds_month": quota_seconds,
            "renewal_at": tenant.renewal_at,
            "created_at": tenant.created_at,
            "allowed_domains": domains,
            "embed_snippet": embed_snippet,
        }

    return response

# --- simple API key guard (prod only)
ALLOWED_KEYS = set([k.strip() for k in os.getenv("ALLOWED_KEYS", "").split(",") if k.strip()])

def dev_bypass_enabled():
    return os.getenv("DEV_BYPASS_TOKEN", "").strip().lower() in ("1","true","yes")

def guard_request(req: Request):
    if dev_bypass_enabled():
        return
    if not DEMO_MODE:
        origin = req.headers.get("origin")
        if ALLOWED and origin not in ALLOWED:
            raise HTTPException(403, "Origin not allowed")
        if ALLOWED_KEYS:
            key = req.headers.get("x-listen-key")
            if not key or key not in ALLOWED_KEYS:
                raise HTTPException(403, "Missing or invalid key")

# --- tiny LRU cache (keeps last 50 items)
class LRU(OrderedDict):
    def __init__(self, cap=50): super().__init__(); self.cap = cap
    def put(self, k, v): 
        if k in self: del self[k]
        super().__setitem__(k, v)
        if len(self) > self.cap: self.popitem(last=False)

cache = LRU()

# --- cache
def cache_key(text: str, voice_id: str) -> str:
    return hashlib.sha1(f"{voice_id}:{text}".encode()).hexdigest()

def tts_hash(text: str, voice_id: str, model_id: str = MODEL_ID) -> str:
    return hashlib.sha1(f"{voice_id}|{model_id}|{text}".encode("utf-8")).hexdigest()

def cache_path(h: str) -> Path:
    return CACHE_DIR / f"{h}.mp3"

def get_lock(h: str) -> asyncio.Lock:
    locks = app.state.locks
    if h not in locks:
        locks[h] = asyncio.Lock()
    return locks[h]

# --- TTS request
class TTSRequest(BaseModel):
    text: str
    
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

# --- Cached, streaming TTS for raw text ---
from fastapi import Query

class TTSBody(BaseModel):
    text: str

@app.get("/tts")
async def tts_get(
    request: Request,
    text: str = Query(..., max_length=20000),
    voice: str | None = Query(None),
    model: str | None = Query(None),
    stability: float = Query(0.35),
    similarity: float = Query(0.9),
    style: float = Query(0.35),
    speaker_boost: bool = Query(True),
    opt_latency: int = Query(2),
):
    tenant_id = get_validated_tenant(request)
    rate_limit_check(request)
    v = voice or os.environ.get("ELEVENLABS_VOICE") or os.environ.get("VOICE_ID") or ""
    if not v:
        raise HTTPException(status_code=400, detail="Voice not provided (and ELEVENLABS_VOICE/VOICE_ID not set).")
    return stream_with_cache(
        text,
        v,
        model or MODEL_ID,
        stability,
        similarity,
        style,
        speaker_boost,
        opt_latency,
        tenant_id=tenant_id,
    )

@app.post("/tts")
def tts_post(
    request: Request,
    body: TTSBody,
    voice: str | None = Query(None),
    model: str | None = Query(None),
    stability: float = Query(0.35),
    similarity: float = Query(0.9),
    style: float = Query(0.35),
    speaker_boost: bool = Query(True),
    opt_latency: int = Query(2),
):
    tenant_id = get_validated_tenant(request, body=body)
    v = voice or os.environ.get("ELEVENLABS_VOICE") or os.environ.get("VOICE_ID") or ""
    if not v:
        raise HTTPException(status_code=400, detail="Voice not provided (and ELEVENLABS_VOICE/VOICE_ID not set).")
    return stream_with_cache(
        body.text,
        v,
        model or MODEL_ID,
        stability,
        similarity,
        style,
        speaker_boost,
        opt_latency,
        tenant_id=tenant_id,
    )

from src.prosody import prepare_article

@app.post("/api/tts")
async def api_tts(
    request: Request,
    body: TTSBody,
    voice: str | None = Query(None),
    model: str | None = Query(None),
    stability: float = Query(0.35),
    similarity: float = Query(0.9),
    style: float = Query(0.35),
    speaker_boost: bool = Query(True),
    opt_latency: int = Query(0),
):
    tenant_id = get_validated_tenant(request, body=body)
    rate_limit_check(request, body=body)
    page_url = request.query_params.get("url") or request.headers.get("referer", "") or ""
    referrer = request.headers.get("referer", "") or ""

    v = (voice or os.environ.get("ELEVENLABS_VOICE") or os.environ.get("VOICE_ID") or "").strip()
    if not v:
        raise HTTPException(400, "Voice not provided (and ELEVENLABS_VOICE/VOICE_ID not set).")

    # Normalize and (optionally) cap for safety
    narrated = prepare_article("", "", body.text or "")
    clean    = preprocess_for_tts(narrated)[:MAX_CHARS]
    text_for_tts = enhance_prosody(clean)

    key  = _cache_key(text_for_tts, v, (model or MODEL_ID), stability, similarity, style, speaker_boost, opt_latency)
    outp = _mp3_path(key)

    # If file exists & non-empty -> HIT
    if outp.exists() and outp.stat().st_size > 0:
        _append_analytics_event("cache_hit", tenant_id, page_url=page_url, referrer=referrer)
        return {
            "audioUrl": public_url(f"/cache/{outp.name}"),
            "hit": True,
            "duration": mp3_duration_seconds(outp) or None,
        }

    quota_state = None
    # MISS: debounce by key so duplicate clicks don't double-spend
    lock = get_lock(key)
    async with lock:
        # re-check after awaiting
        if outp.exists() and outp.stat().st_size > 0:
            _append_analytics_event("cache_hit", tenant_id, page_url=page_url, referrer=referrer)
            return {
                "audioUrl": public_url(f"/cache/{outp.name}"),
                "hit": True,
                "duration": mp3_duration_seconds(outp) or None,
            }

        # Quota check is done right before a new render to avoid burning credits on rejects.
        quota_state = ensure_tenant_quota_ok(tenant_id, request=request)
        try:
            data = await tts_bytes(text_for_tts, v, (model or MODEL_ID))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Provider error: {e}")

        tmp = outp.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(outp)

    duration = mp3_duration_seconds(outp)
    if not duration:
        duration = estimate_seconds_from_text(text_for_tts)
    if duration:
        record_tenant_usage_seconds(tenant_id, duration)
    _append_analytics_event("cache_miss", tenant_id, page_url=page_url, referrer=referrer)

    return {
        "audioUrl": public_url(f"/cache/{outp.name}"),
        "hit": False,
        "duration": duration or None,
        "quota": quota_state.get("quota") if quota_state else None,
        "usedSeconds": quota_state.get("used") if quota_state else None,
    }

APP_URL = os.getenv("APP_URL","").rstrip("/")  # e.g., https://your-service.onrender.com
def public_url(path: str) -> str:
    return f"{APP_URL}{path}" if APP_URL else path


def prepare_article(title: str, author: str, text: str) -> str:
    parts = []
    if title:  parts.append(f"{title}.")
    if author: parts.append(f"By {author}.")
    if text:   parts.append(text)
    return " ".join(parts)

@app.get("/debug/config")
def debug_config():
    from os import getenv
    key = getenv("ELEVENLABS_API_KEY", "")
    db_url = getenv("DATABASE_URL", "").strip()
    db_path = getenv("TENANT_DB_PATH", "/cache/tenants.db")
    tenants_db = "DATABASE_URL" if db_url else f"sqlite:{db_path}"
    return {
        "has_api_key": bool(key),
        "api_key_head": (key[:4] + "…" if key else None),
        "voice_id": VOICE_ID,
        "model_id": MODEL_ID,
        "tenant_auth_mode": "db_allowlist_exact_domains",
        "demo_mode": DEMO_MODE,
        "require_domain_header": not DEMO_MODE,
        "tenants_db": tenants_db,
    }


@app.get("/read")
async def read(request: Request, url: str, voice: str | None = None, model: str | None = None):
    # sanity: key/voice present
    tenant_id = get_validated_tenant(request)
    ensure_tenant_quota_ok(tenant_id, request=request)
    if not API_KEY:
        raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY is missing")
    v = (voice or VOICE_ID or "").strip()
    if not v:
        raise HTTPException(status_code=400, detail="voice id is required (dataset.voice or VOICE_ID)")

    # 1) Extract + prepare
    title, author, text = extract_article(url)
    cleaned = preprocess_for_tts(text or "")
    narration = prepare_article(title, author, cleaned)
    if not narration or len(narration.strip()) < 40:
        raise HTTPException(status_code=422, detail="No narratable text extracted from page")

    # 2) Safe sentence chunks (small enough to never 502)
    parts = chunk_by_sentence(narration, target=900, hard_max=1200)
    if not parts:
        raise HTTPException(status_code=422, detail="No narratable chunks produced")

    # 3) Fetch each part to BYTES and concat
    m = model or MODEL_ID
    bufs: list[bytes] = []
    for i, part in enumerate(parts):
        try:
            processed_part = enhance_prosody(preprocess_for_tts(part))
            audio = await tts_bytes(processed_part, v, m)
            bufs.append(audio)
            print({"event":"read_part_ok","i":i,"bytes":len(audio)})
        except Exception as e:
            # stop cleanly; we'll still return what we have
            print({"event":"read_part_fail","i":i,"err":str(e)[:300]})
            break

    merged = b"".join(bufs)
    if not merged:
        raise HTTPException(status_code=502, detail="Upstream produced no audio for any chunk")
    est = estimate_seconds_from_text(narration)
    if est:
        record_tenant_usage_seconds(tenant_id, est)

    return Response(content=merged, media_type="audio/mpeg")

# --- extract
def is_public_http_url(u:str)->bool:
    try:
        p=urlparse(u)
        if p.scheme not in ("http","https"): return False
        # block local/lan
        host=p.hostname or ""
        if host.endswith((".local",".lan")) or host in ("localhost","127.0.0.1"): return False
        # resolve and block private/link-local/multicast/broadcast
        try:
            infos = socket.getaddrinfo(host, None)
            for fam,_,_,_,sockaddr in infos:
                ip = sockaddr[0]
                ip_obj = ipaddress.ip_address(ip)
                if (
                    ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or
                    ip_obj.is_multicast or ip_obj.is_reserved
                ):
                    return False
        except Exception:
            return False
        return True
    except: return False

async def stream_tts_for_text(text: str, voice_id: str = VOICE_ID, model_id: str = MODEL_ID,
                              voice_settings: dict | None = None, tone: str = "neutral"):
    if STUB_TTS:
        # Always serve a local file for demos
        from fastapi.responses import FileResponse
        # use the one already in your repo (root) or put one in /static
        demo_file = Path("ok.mp3")
        if not demo_file.exists():
            demo_file = Path("static/ok.mp3")
        return FileResponse(demo_file, media_type="audio/mpeg", headers={"X-Demo":"1"})
        # memory/disk cache paths ... (keep your existing code)

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {"xi-api-key": API_KEY, "Accept": "audio/mpeg", "Content-Type": "application/json"}
    prepared_text = enhance_prosody(preprocess_for_tts(text))

    payload = {
        "text": prepared_text,
        "model_id": model_id,
        "voice_settings": voice_settings or {
            "stability": 0.45,
            "similarity_boost": 0.85,
            "style": 0.60,
            "use_speaker_boost": True,
        },
        "optimize_streaming_latency": 2,
    }

    start_time = time.time()
    first_chunk_time = None
    total_bytes = 0
    buf = bytearray()
    tmp_path = p.with_suffix(".part")

    # Start the stream *here* so we can check status before returning SR
    resp = await client.stream("POST", url, headers=headers, json=payload)

    if resp.status_code != 200:
        err = await resp.aread()
        await resp.aclose()
        # Surface as a real error (not empty 200)
        # You can also: return PlainTextResponse(err, status_code=resp.status_code)
        raise HTTPException(status_code=502, detail=(err.decode("utf-8", "ignore")[:300] or "TTS upstream error"))

    async def gen():
        nonlocal first_chunk_time, total_bytes
        try:
            with tmp_path.open("wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    if not chunk:
                        continue
                    if first_chunk_time is None:
                        first_chunk_time = time.time()
                    total_bytes += len(chunk)
                    buf.extend(chunk)
                    f.write(chunk)
                    yield chunk
        finally:
            try:
                await resp.aclose()
            except Exception:
                pass
            first_ms = int(((first_chunk_time or time.time()) - start_time) * 1000)
            print({"event": "tts_stream", "first_audio_ms": first_ms, "total_bytes": total_bytes, "hash": h, "tone": tone})
            try:
                write_stream_row(int(time.time()*1000), "api", first_ms, total_bytes, model_id, h)
            except Exception:
                pass
            if total_bytes > 0:
                try:
                    tmp_path.replace(p)
                    cache.put(h, bytes(buf))
                except Exception as e:
                    print({"event":"cache_finalize_error","err":str(e)})

    return StreamingResponse(gen(), media_type="audio/mpeg", headers={"x-cache-hit": "false"})

# --- Caching metrics and unified streamer
MAX_CACHE_BYTES = int(os.getenv("CACHE_MAX_BYTES", str(2 * 1024**3)))
MAX_CACHE_FILES = int(os.getenv("CACHE_MAX_FILES", "2000"))

metrics = {
    "tts_requests": 0,
    "tts_errors": 0,
    "tts_cache_hits": 0,
    "tts_cache_misses": 0,
    "tts_first_byte_ms": [],
}

def _cache_inventory():
    total = 0
    items = []
    for name in os.listdir(CACHE_DIR):
        if not name.endswith(".mp3"):
            continue
        p = os.path.join(CACHE_DIR, name)
        try:
            st = os.stat(p)
        except FileNotFoundError:
            continue
        items.append((st.st_mtime, p, st.st_size))
        total += st.st_size
    items.sort(key=lambda x: x[0])
    return total, items

def get_cache_stats():
    total, items = _cache_inventory()
    return {
        "files": len(items),
        "bytes": total,
        "bytes_gb": round(total / (1024**3), 3),
        "oldest_ts": items[0][0] if items else None,
        "newest_ts": items[-1][0] if items else None,
        "budget_bytes": MAX_CACHE_BYTES,
        "budget_files": MAX_CACHE_FILES,
    }

def enforce_cache_budget(max_bytes=MAX_CACHE_BYTES, max_files=MAX_CACHE_FILES):
    total, items = _cache_inventory()
    evicted = 0
    removed_bytes = 0
    i = 0
    while (total - removed_bytes) > max_bytes or (max_files and (len(items) - evicted) > max_files):
        if i >= len(items):
            break
        _, path, sz = items[i]
        i += 1
        try:
            os.remove(path)
            evicted += 1
            removed_bytes += sz
        except FileNotFoundError:
            pass
    return {"evicted": evicted, "bytes_freed": removed_bytes}

def stream_with_cache(text: str, voice: str, model: str,
                      stability: float, similarity: float, style: float,
                      speaker_boost: bool, opt_latency: int,
                      tenant_id: str | None = None):
    """
    Streams TTS audio from ElevenLabs, with:
      - preflight status check (no streaming starts if upstream is an error)
      - first-chunk prefetch (we have a chunk before returning StreamingResponse)
      - never-raise-after-yield (avoid 'response already started' runtime error)
      - write-through cache with budget eviction
    """
    metrics["tts_requests"] += 1
    clean = preprocess_for_tts(text)
    tts_input = enhance_prosody(clean)

    key  = _cache_key(tts_input, voice, model, stability, similarity, style, speaker_boost, opt_latency)
    path = os.path.join(CACHE_DIR, f"{key}.mp3")
    if os.path.exists(path):
        metrics["tts_cache_hits"] += 1
        dur = mp3_duration_seconds(Path(path))
        headers = {"X-Cache": "HIT"}
        if dur:
            headers["X-AIL-Duration"] = str(dur)
        write_stream_row(int(time.time()*1000), "HIT", 0, os.path.getsize(path), model, os.path.basename(path).split(".")[0])
        return FileResponse(path, media_type="audio/mpeg", headers=headers)

    metrics["tts_cache_misses"] += 1
    quota_state = None
    if tenant_id:
        quota_state = ensure_tenant_quota_ok(tenant_id)

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream"
    headers = {
        "xi-api-key": os.environ.get("ELEVENLABS_API_KEY", ""),
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    payload = {
        "text": tts_input,
        "model_id": model,
        "optimize_streaming_latency": int(opt_latency),
        "voice_settings": {
            "stability": float(stability),
            "similarity_boost": float(similarity),
            "style": float(style),
            "use_speaker_boost": bool(speaker_boost),
        },
    }

    try:
        r = http.post(url, headers=headers, json=payload, stream=True, timeout=60)
    except Exception as e:
        metrics["tts_errors"] += 1
        raise HTTPException(status_code=502, detail=f"Upstream connection failed: {e}")

    if r.status_code in (401, 402, 429):
        metrics["tts_errors"] += 1
        raise HTTPException(status_code=429, detail=f"Upstream TTS error {r.status_code}. Check key/credits/limits.")
    try:
        r.raise_for_status()
    except Exception as e:
        metrics["tts_errors"] += 1
        raise HTTPException(status_code=502, detail=f"TTS upstream error: {e}")

    start = time.time()
    chunk_iter = r.iter_content(32 * 1024)
    first_chunk = None
    try:
        for c in chunk_iter:
            if c:
                first_chunk = c
                metrics["tts_first_byte_ms"].append(int((time.time() - start) * 1000))
                break
    except Exception as e:
        metrics["tts_errors"] += 1
        raise HTTPException(status_code=502, detail=f"TTS fetch failed before first audio: {e}")

    if not first_chunk:
        metrics["tts_errors"] += 1
        raise HTTPException(status_code=502, detail="Upstream produced no audio.")

    tmp = path + ".part"

    def gen():
        complete = False
        try:
            with open(tmp, "wb") as f:
                f.write(first_chunk)
                yield first_chunk
                for c in chunk_iter:
                    if not c:
                        continue
                    f.write(c)
                    yield c
            os.replace(tmp, path)
            complete = True
            enforce_cache_budget()
            write_stream_row(
                int(time.time()*1000),
                "MISS",
                metrics["tts_first_byte_ms"][-1] if metrics["tts_first_byte_ms"] else 0,
                os.path.getsize(path),
                model,
                key
            )
            if tenant_id:
                duration = mp3_duration_seconds(Path(path))
                if not duration:
                    duration = estimate_seconds_from_text(tts_input)
                if duration:
                    record_tenant_usage_seconds(tenant_id, duration)
        except Exception:
            try:
                if not complete and os.path.exists(tmp):
                    os.remove(tmp)
            except:
                pass
            return

    return StreamingResponse(gen(), media_type="audio/mpeg", headers={"X-Cache": "MISS"})

def _cache_key(text: str, voice: str, model: str,
               stability: float, similarity: float, style: float,
               speaker_boost: bool, opt_latency: int) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    h.update(f"|{voice}|{model}|{stability}|{similarity}|{style}|{speaker_boost}|{opt_latency}".encode())
    return h.hexdigest()

# --- precaching helpers ---
def _cache_key_simple(text: str, voice: str) -> str:
    return hashlib.sha256(f"{voice}|{text}".encode("utf-8")).hexdigest()

def _mp3_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.mp3"


def compute_article_hash(tenant_id: str, text: str, voice_id: str, model_id: str) -> str:
    payload = {
        "tenant": tenant_id,
        "text": text,
        "voice": voice_id or "",
        "model": model_id or "",
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def article_mp3_path(hash_value: str) -> Path:
    """Return the absolute path for a cached article MP3 on the persistent disk.

    NOTE: This MUST live under CACHE_ROOT so files survive restarts and deploys.
    """
    return CACHE_ROOT / f"{hash_value}.mp3"


# Cache HIT vs MISS is determined solely by MP3 file existence on disk.
# Logs emitted here are informational only; they do not change control flow.
async def ensure_article_cached(
    hash_value: str,
    *,
    text: str,
    tenant_id: str,
    voice_id: str,
    model_id: str,
) -> Path:
    """
    Ensure the article audio for `hash` is present on disk.

    - If the MP3 already exists at article_mp3_path(hash), treat as a CACHE HIT and DO NOT call ElevenLabs.
    - If it does not exist, call ElevenLabs once, stream to a temp file, then atomically move to the final path.

    Returns:
        Path to the cached MP3 on disk.
    """

    clean = (text or "").strip()
    if not clean:
        raise HTTPException(status_code=422, detail="Empty article text")
    clean = clean[:MAX_CHARS]
    tts_ready = enhance_prosody(clean)
    if not tts_ready:
        raise HTTPException(status_code=422, detail="Empty article text")

    mp3_path = article_mp3_path(hash_value)
    lock = get_lock(hash_value)
    task = asyncio.current_task()

    def _mark_cache_status(hit: bool) -> None:
        if task is not None:
            setattr(task, "_article_cache_hit", hit)

    if mp3_path.exists() and mp3_path.stat().st_size > 0:
        logger.info(
            "[cache] article_cache_hit hash=%s path=%s",
            hash_value,
            mp3_path,
        )
        logger.info(
            "[cache] HIT",
            extra={"hash": hash_value, "mp3_path": str(mp3_path)},
        )
        _mark_cache_status(True)
        return mp3_path

    async with lock:
        if mp3_path.exists() and mp3_path.stat().st_size > 0:
            logger.info(
                "[cache] article_cache_hit hash=%s path=%s",
                hash_value,
                mp3_path,
            )
            logger.info(
                "[cache] HIT",
                extra={"hash": hash_value, "mp3_path": str(mp3_path)},
            )
            _mark_cache_status(True)
            return mp3_path

        # Quota enforcement happens only on cache miss just before rendering.
        ensure_tenant_quota_ok(tenant_id)
        logger.info(
            "[cache] article_cache_miss hash=%s path=%s; generating via ElevenLabs",
            hash_value,
            mp3_path,
        )
        logger.info(
            "[cache] MISS -> render",
            extra={"hash": hash_value, "mp3_path": str(mp3_path), "tenant": tenant_id},
        )
        try:
            data = await tts_bytes(tts_ready, voice_id, model_id)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Provider error: {e}")

        tmp = mp3_path.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(mp3_path)
        size = mp3_path.stat().st_size
        duration = mp3_duration_seconds(mp3_path)
        if not duration:
            duration = estimate_seconds_from_text(tts_ready)
        if duration:
            record_tenant_usage_seconds(tenant_id, duration)
        logger.info(
            "[cache] WRITE complete",
            extra={"hash": hash_value, "mp3_path": str(mp3_path), "bytes": size},
        )
        _mark_cache_status(False)
        return mp3_path

# Reuse your synth function used by /api/tts, e.g. synth_to_file(text, voice, out_path)
async def elevenlabs_tts_to_file(text: str, voice: str, out_path: Path) -> str:
    """Synthesize text to speech and save to file, returns the URL path"""
    try:
        data = await tts_bytes(text, voice, MODEL_ID)
        with open(out_path, "wb") as f:
            f.write(data)
        return f"/cache/{out_path.name}"
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TTS synthesis failed: {e}")

class PrecacheReq(BaseModel):
    text: str
    voice: Optional[str] = None

_precache_lock = Lock()

@app.post("/precache_text")
async def precache_text(req: PrecacheReq, request: Request):
    tenant_id = get_validated_tenant(request, body=req)
    voice = req.voice or os.getenv("VOICE_ID", "")
    if not req.text.strip():
        raise HTTPException(400, "text required")
    prepared = enhance_prosody(preprocess_for_tts(req.text))
    key = _cache_key_simple(prepared, voice)
    outp = _mp3_path(key)
    created = False
    duration = mp3_duration_seconds(outp) if outp.exists() else None
    with _precache_lock:
        if not outp.exists():
            ensure_tenant_quota_ok(tenant_id, request=request)
            await elevenlabs_tts_to_file(prepared, voice, outp)
            created = True
            duration = mp3_duration_seconds(outp)
            if not duration:
                duration = estimate_seconds_from_text(prepared)
            if duration:
                record_tenant_usage_seconds(tenant_id, duration)
    if duration is None and outp.exists():
        duration = mp3_duration_seconds(outp)
    if not duration:
        duration = estimate_seconds_from_text(prepared)
    return {
        "ok": True,
        "created": created,
        "audioUrl": f"/cache/{outp.name}",
        "duration": duration or None,
        "tenant": tenant_id,
    }

@app.get("/precache_status")
def precache_status(text: str, voice: Optional[str] = None):
    voice = voice or os.getenv("VOICE_ID", "")
    prepared = enhance_prosody(preprocess_for_tts(text))
    key = _cache_key_simple(prepared, voice)
    outp = _mp3_path(key)
    return {"ok": True, "exists": outp.exists(), "audioUrl": f"/cache/{outp.name}" if outp.exists() else None}

@app.get("/cache/stats")
def cache_stats():
    s = get_cache_stats()
    return {**s, "hits": metrics["tts_cache_hits"], "misses": metrics["tts_cache_misses"]}

# --- Stripe provisioning helpers ---
TENANT_STORE = Path("/cache/tenants.json")
NOTIFY_STORE = Path("/cache/notify.json")


def _public_base_from_request(request: Request | None = None) -> str:
    if PUBLIC_API_BASE:
        return PUBLIC_API_BASE.rstrip("/")
    if request is not None:
        try:
            url = request.url
            base = f"{url.scheme}://{url.netloc}"
            if base:
                return base.rstrip("/")
        except Exception:
            pass
    env_app_url = os.getenv("APP_URL", "").rstrip("/")
    if env_app_url:
        return env_app_url
    return ""


def _widget_src_url(public_base: str) -> str:
    if PUBLIC_WIDGET_URL:
        return PUBLIC_WIDGET_URL
    if public_base:
        return f"{public_base}/static/tts-widget.v1.js"
    return "/static/tts-widget.v1.js"

def _tier_from_price(price_id: str) -> str | None:
    if not price_id:
        return None
    if price_id == PRICE_CREATOR_ID:
        return "creator"
    if price_id == PRICE_PUBLISHER_ID:
        return "publisher"
    if price_id == PRICE_NEWSROOM_ID:
        return "newsroom"
    return None

def _load_tenant_store() -> dict:
    if not TENANT_STORE.exists():
        return {}
    try:
        return json.loads(TENANT_STORE.read_text("utf-8"))
    except Exception:
        return {}

def _save_tenant_store(data: dict) -> None:
    TENANT_STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = TENANT_STORE.with_suffix(".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(TENANT_STORE)

def _load_notify_store() -> dict:
    if not NOTIFY_STORE.exists():
        return {}
    try:
        return json.loads(NOTIFY_STORE.read_text("utf-8"))
    except Exception:
        return {}


def _save_notify_store(data: dict) -> None:
    NOTIFY_STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = NOTIFY_STORE.with_suffix(".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(NOTIFY_STORE)


def _email_for_tenant(tenant_key: str) -> str | None:
    store = _load_tenant_store()
    for email, meta in store.items():
        if isinstance(meta, dict) and meta.get("tenant_key") == tenant_key:
            return email
    return None


def _maybe_send_quota_email(tenant: Tenant, quota: int, request: Request | None = None) -> bool:
    if not RESEND_API_KEY or not EMAIL_FROM:
        return False
    to_email = _email_for_tenant(tenant.tenant_key)
    if not to_email:
        return False
    now = datetime.now(timezone.utc)
    notify = _load_notify_store()
    last_raw = notify.get(tenant.tenant_key)
    if last_raw:
        try:
            last_dt = datetime.fromisoformat(last_raw)
            if now - last_dt < timedelta(hours=24):
                return False
        except Exception:
            pass
    public_base = _public_base_from_request(request)
    site_url = public_base or os.getenv("APP_URL", "").rstrip("/")
    safe_site = escape(site_url) if site_url else None
    cta = (
        f'<p><a href="{safe_site}">Upgrade your plan</a> or reply to this email if you need help.</p>'
        if safe_site
        else "<p>Reply to this email to upgrade your plan or ask for help.</p>"
    )
    plan_label = (tenant.plan_tier or "trial").title()
    html = (
        f"<p>You reached the monthly render limit for the {escape(plan_label)} plan.</p>"
        f"<p>Already-generated audio will keep playing for your readers.</p>"
        f"<p>Plan limit: {int(quota)} seconds. Used: {int(tenant.used_seconds_month)} seconds.</p>"
        f"{cta}"
    )
    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": EMAIL_FROM,
                "to": [to_email],
                "subject": "EasyAudio quota reached",
                "html": html,
            },
            timeout=10,
        )
        resp.raise_for_status()
        notify[tenant.tenant_key] = now.isoformat()
        _save_notify_store(notify)
        return True
    except Exception as e:
        logger.warning("quota notify send failed: %s", e)
        return False


async def _send_resend_email(to_email: str, tenant_key: str, tier: str, request: Request | None = None) -> bool:
    if not RESEND_API_KEY or not EMAIL_FROM or not to_email:
        return False
    public_base = _public_base_from_request(request)
    widget_src = _widget_src_url(public_base)
    plan_label = (tier or "trial").title()
    calendly_url = "https://calendly.com/henry10greene/30min"
    help_line = (
        f'<p>If you need help installing, book a free installation:<br>'
        f'<a href="{calendly_url}">{calendly_url}</a></p>'
    )
    snippet = f"""<script
  src="{widget_src}"
  data-ail-api-base="{public_base}"
  data-ail-tenant="{tenant_key}">
</script>"""
    html = (
        "<p>Welcome to EasyAudio.</p>"
        "<p>EasyAudio converts your articles to audio for your readers.</p>"
        f"{help_line}"
        f"<p>Your plan: <strong>{escape(plan_label)}</strong></p>"
        f"<p>Tenant key:</p><pre><code>{escape(tenant_key)}</code></pre>"
        f"<p>Install snippet:</p><pre><code>{escape(snippet)}</code></pre>"
        "<p>Paste this snippet right before the closing &lt;/body&gt; tag on the page where you want the Listen button to appear.</p>"
        "<p>After checkout, you'll receive a unique key. (check spam)</p>"
    )
    client: httpx.AsyncClient = app.state.http_client
    try:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": EMAIL_FROM,
                "to": [to_email],
                "subject": "Welcome to EasyAudio - your embed is ready",
                "html": html,
                "tracking": {"clicks": False},
            },
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("resend email failed: %s", e)
        return False

def _ensure_tenant_for_email(email: str, tier: str, stripe_customer_id: str | None = None) -> tuple[str, bool]:
    """Return (tenant_key, is_new)."""
    email_key = (email or "").strip().lower()
    store = _load_tenant_store()
    if email_key in store and store[email_key].get("tenant_key"):
        return store[email_key]["tenant_key"], False
    tenant_key = f"tnt_{secrets.token_urlsafe(12)}"
    store[email_key] = {
        "tenant_key": tenant_key,
        "tier": tier,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stripe_customer_id": stripe_customer_id,
    }
    try:
        _save_tenant_store(store)
    except Exception as e:
        logger.warning("tenant store write failed: %s", e)
    return tenant_key, True


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        logger.warning("stripe webhook verify failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid signature")
    event_type = event.get("type")
    logger.info("[stripe] event received type=%s", event_type)

    if event_type == "checkout.session.completed":
        session_obj = event.get("data", {}).get("object", {})
        session_id = session_obj.get("id")
        try:
            full_session = stripe.checkout.Session.retrieve(
                session_id,
                expand=["line_items.data.price"],
            )
        except Exception as e:
            logger.warning("stripe session retrieve failed: %s", e)
            return JSONResponse({"ok": True})

        cust_email = (
            (full_session.get("customer_details") or {}).get("email")
            or full_session.get("customer_email")
        )
        if not cust_email:
            logger.warning("stripe checkout.completed missing email for session=%s", session_id)
            return JSONResponse({"ok": True})
        line_items = (full_session.get("line_items") or {}).get("data") or []
        first = line_items[0] if line_items else {}
        price = (first.get("price") or {}) if isinstance(first, dict) else {}
        price_id = price.get("id")
        interval = (price.get("recurring") or {}).get("interval")
        logger.info(
            "[stripe] checkout.session.completed email=%s price_id=%s interval=%s",
            cust_email,
            price_id,
            interval,
        )
        tier = _tier_from_price(price_id)
        if not tier:
            logger.error("stripe webhook unknown price_id=%s", price_id)
            return JSONResponse({"ok": True})
        tenant_key, _created = _ensure_tenant_for_email(
            cust_email,
            tier,
            stripe_customer_id=full_session.get("customer"),
        )
        emailed = await _send_resend_email(cust_email, tenant_key, tier, request=request)
        logger.info(
            "[provision] email=%s tier=%s tenant_key=%s emailed=%s",
            cust_email,
            tier,
            tenant_key,
            emailed,
        )
    return JSONResponse({"ok": True})

@app.post("/cache/evict")
def cache_evict():
    return enforce_cache_budget()

@app.delete("/cache")
def cache_clear():
    n = 0
    for name in os.listdir(CACHE_DIR):
        if not name.endswith(".mp3"):
            continue
        p = os.path.join(CACHE_DIR, name)
        try:
            os.remove(p); n += 1
        except FileNotFoundError:
            pass
    return {"cleared": n}

@app.get("/metrics")
def get_metrics():
    arr = metrics["tts_first_byte_ms"]
    avg_fb = int(sum(arr) / max(1, len(arr))) if arr else None
    cache = get_cache_stats()
    return {
        "tts_requests": metrics["tts_requests"],
        "tts_errors": metrics["tts_errors"],
        "tts_cache_hits": metrics["tts_cache_hits"],
        "tts_cache_misses": metrics["tts_cache_misses"],
        "avg_first_byte_ms": avg_fb,
        "cache_files": cache["files"],
        "cache_bytes_gb": cache["bytes_gb"],
    }


@app.get("/tenants/stats")
def tenants_stats():
    """Expose current tenant quota config + usage for debugging."""
    with tenant_session() as session:
        rows = list_tenants(session)
        data = [
            {
                "tenant_key": t.tenant_key,
                "plan_tier": t.plan_tier,
                "used_seconds_month": t.used_seconds_month,
                "quota_seconds_month": quota_for_plan(t.plan_tier),
                "renewal_at": t.renewal_at,
                "created_at": t.created_at,
            }
            for t in rows
        ]
    return {"tenants": data}

# --- TTS request (streaming via shared function)
@app.post("/tts")
async def tts(req: TTSRequest, request: Request):
    tenant_id = get_validated_tenant(request, body=req)
    guard_request(request)
    sample_text = (
        "This is a short sample paragraph to verify streaming text to speech. "
        "Audio should begin quickly and continue without interruption."
    )
    text = (getattr(req, "text", "") or "").strip() or sample_text
    return stream_with_cache(
        text,
        VOICE_ID,
        MODEL_ID,
        0.35,
        0.75,
        0.40,
        True,
        2,
        tenant_id=tenant_id,
    )

# --- TTS GET for direct <audio src>
@app.get("/tts")
def tts(
    request: Request,
    text: str = Query(..., max_length=20000),
    voice: str | None = Query(None),
    model: str = Query("eleven_turbo_v2"),
    stability: float = Query(0.35),
    similarity: float = Query(0.75),
    style: float = Query(0.40),
    speaker_boost: bool = Query(True),
    opt_latency: int = Query(2),
):
    tenant_id = get_validated_tenant(request)
    voice = voice or os.environ.get("ELEVENLABS_VOICE", "")
    if not voice:
        raise HTTPException(status_code=400, detail="Voice not provided (and ELEVENLABS_VOICE not set).")
    return stream_with_cache(
        text,
        voice,
        model,
        stability,
        similarity,
        style,
        speaker_boost,
        opt_latency,
        tenant_id=tenant_id,
    )

@app.get("/favicon.ico")
def _favicon():
    return Response(status_code=204)

# --- extract
@app.get("/extract")
def extract(url: str = Query(..., min_length=8), request: Request = None):
    if request is not None:
        guard_request(request)
    if not is_public_http_url(url):
        raise HTTPException(400, "Invalid URL")
    try:
        r = http.get(url, timeout=8, headers={"User-Agent":"Mozilla/5.0 (ReaderBot)"})
        if r.status_code != 200 or not r.text:
            raise HTTPException(502, "Fetch failed")
        extracted = trafilatura.extract(r.text, include_comments=False, include_tables=False,
                                favor_precision=True)
        if not extracted:
            raise HTTPException(422, "No article content found")

        # simple <title> fallback from the HTML
        m = re.search(r"<title[^>]*>(.*?)</title>", r.text, flags=re.I|re.S)
        title = (m.group(1).strip() if m else "")
        text = extracted.strip()

        # basic cleanup
        text = re.sub(r'\n{3,}', '\n\n', text)
        return {"title": title, "text": text[:200000]}  # hard cap
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(500, f"Extract error")
    
# --- prosody: add pauses/structure
def prosody(title: str, body: str) -> str:
    t = (title or "").strip()
    b = (body or "").strip()
    head = f"{t}.\n\n" if t else ""
    # tighten spacing, add paragraph pauses
    b = re.sub(r'\n{3,}', '\n\n', b)
    return head + b
CAPTION_HINTS = (
    "photograph by", "photo by", "image:", "video:", "illustration by",
    "getty images", "ap photo", "reuters", "courtesy", "via", "credit:"
)

def looks_like_caption(line: str) -> bool:
    s = line.strip()
    if not s: return True
    if len(s) < 40: return True
    low = s.lower()
    return any(h in low for h in CAPTION_HINTS)

def strip_captions(text: str) -> str:
    parts = [p.strip() for p in re.split(r"\n{1,}", text)]
    keep = [p for p in parts if not looks_like_caption(p)]
    return "\n\n".join(keep)

def find_author_from_meta(html: str) -> str | None:
    m = re.search(r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']+)["\']', html, flags=re.I)
    if m: return m.group(1).strip()
    m = re.search(r'"author"\s*:\s*"\s*([^"]+)\s*"', html, flags=re.I)
    if m: return m.group(1).strip()
    m = re.search(r'"author"\s*:\s*{\s*"@type"\s*:\s*"Person"\s*,\s*"name"\s*:\s*"([^"]+)"', html, flags=re.I)
    if m: return m.group(1).strip()
    return None

def build_read_text(title: str, body: str, author: str | None) -> str:
    intro = f"Now reading: {title}.\n\n" if title else ""
    core = strip_captions(body)
    outro = f"\n\nArticle by {author}." if author else ""
    core = re.sub(r'\n{3,}', '\n\n', core)
    return intro + core + outro

# --- helpers for /meta (title/subtitle/author/cover) ---
def _meta_clean(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()

def find_subtitle(html: str) -> str | None:
    m = re.search(r'<h2[^>]*>(.*?)</h2>', html, flags=re.I|re.S)
    if m:
        return _meta_clean(re.sub(r'<[^>]+>', '', m.group(1)))
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html, flags=re.I)
    return _meta_clean(m.group(1)) if m else None

def find_author(html: str) -> str | None:
    m = re.search(r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']+)["\']', html, flags=re.I)
    if m: return _meta_clean(m.group(1))
    m = re.search(r'"author"\s*:\s*"\s*([^"]+)\s*"', html, flags=re.I)
    if m: return _meta_clean(m.group(1))
    m = re.search(r'"author"\s*:\s*{\s*"@type"\s*:\s*"Person"\s*,\s*"name"\s*:\s*"([^"]+)"', html, flags=re.I)
    if m: return _meta_clean(m.group(1))
    m = re.search(r'>\s*By\s+([A-Z][A-Za-z0-9.\- ]+)\s*<', html, flags=re.I)
    return _meta_clean(m.group(1)) if m else None

def find_og_image(html: str) -> str | None:
    m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, flags=re.I)
    return m.group(1).strip() if m else None

@app.get("/meta")
def meta(url: str = Query(..., min_length=8)):
    if not is_public_http_url(url):
        raise HTTPException(400, "Invalid URL")
    try:
        r = http.get(url, timeout=8, headers={"User-Agent":"Mozilla/5.0 (ReaderBot)"})
        if r.status_code != 200 or not r.text:
            raise HTTPException(502, "Fetch failed")
        html = r.text

        mt = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I|re.S)
        title = _meta_clean(mt.group(1)) if mt else ""
        return {
            "title": title,
            "subtitle": find_subtitle(html),
            "author": find_author(html),
            "image": find_og_image(html),
        }
    except HTTPException: raise
    except Exception:
        raise HTTPException(500, "Meta error")

# --- Prosody tone 1.0
NEG = {"dies","dead","death","shooting","war","massacre","earthquake","flood","famine","injured","tragedy","lawsuit","bankrupt","recall","layoffs","crash","toxic","drought","meltdown"}
POS = {"record","soared","booming","surge","breakthrough","discovery","wins","celebrates","milestone","landmark","thrilled","optimistic"}

def pick_tone(title: str, body: str) -> str:
    t = (title or "").lower(); b = (body or "").lower()
    n = sum(w in t or w in b for w in NEG); p = sum(w in t or w in b for w in POS)
    if n > p and n >= 2: return "somber"
    if p > n and p >= 2: return "upbeat"
    return "neutral"

def shape_text_for_tone(text: str, tone: str) -> tuple[str, dict]:
    if tone == "somber":
        shaped = re.sub(r",\s*", ", … ", text)
        shaped = re.sub(r"[:;]\s*", ". ", shaped)
        settings = {"stability":0.25,"similarity_boost":0.9,"style":0.2,"use_speaker_boost":True}
    elif tone == "upbeat":
        shaped = re.sub(r"\.\s+", ". ", text)
        settings = {"stability":0.45,"similarity_boost":0.9,"style":0.5,"use_speaker_boost":True}
    else:
        shaped = text
        settings = {"stability":0.35,"similarity_boost":0.9,"style":0.35,"use_speaker_boost":True}
    shaped = re.sub(r"\n{3,}", "\n\n", shaped)
    return shaped, settings

# --- article audio cache API ---
class ArticleAudioRequest(BaseModel):
    url: str | None = None
    text: str | None = None
    href: str | None = None

# Manual test:
# POST the same text twice → first call MISS, second HIT, same audio output.
@app.post("/api/article-audio")
async def article_audio(req: ArticleAudioRequest, request: Request):
    tenant_id, tenant = get_validated_tenant_record(request, body=req)
    enforce_domain_allowlist(request, tenant, tenant_id)
    tenant_cfg = VOICE_TENANTS.get(tenant_id) or VOICE_TENANTS.get("default")

    raw_text = (req.text or "").strip()

    if not raw_text and req.url:
        title, author, text = extract_article(req.url)
        cleaned = preprocess_for_tts(text or "")
        raw_text = prepare_article(title, author, cleaned)

    if not raw_text:
        raise HTTPException(status_code=400, detail="Must provide url or text")

    canonical = (preprocess_for_tts(raw_text) or "").strip()
    if not canonical:
        raise HTTPException(status_code=422, detail="Empty article text")
    canonical = canonical[:MAX_CHARS]

    canonical, truncated = enforce_article_length_limit(tenant_id, canonical)
    if truncated:
        logger.info(
            "[quota] trial preview audio truncated for tenant=%s; full article exceeds trial per-article limit",
            tenant_id,
        )

    voice_id = (
        (tenant_cfg.voice_id if tenant_cfg else "")
        or os.environ.get("ELEVENLABS_VOICE")
        or os.environ.get("VOICE_ID")
        or ""
    ).strip()
    if not voice_id:
        raise HTTPException(status_code=400, detail="Voice not provided (and ELEVENLABS_VOICE/VOICE_ID not set).")
    model_id = (tenant_cfg.model_id if tenant_cfg and tenant_cfg.model_id else MODEL_ID).strip()

    hash_value = compute_article_hash(tenant_id, canonical, voice_id, model_id)
    mp3_path = article_mp3_path(hash_value)
    logger.info(
        "[cache] request",
        extra={"tenant": tenant_id, "hash": hash_value, "mp3_path": str(mp3_path)},
    )

    mp3_path = await ensure_article_cached(
        hash_value,
        text=canonical,
        tenant_id=tenant_id,
        voice_id=voice_id,
        model_id=model_id,
    )

    task = asyncio.current_task()
    was_cached = False
    if task is not None and hasattr(task, "_article_cache_hit"):
        was_cached = bool(getattr(task, "_article_cache_hit"))
        delattr(task, "_article_cache_hit")
    duration = mp3_duration_seconds(mp3_path)

    headers = {
        "X-Cache": "HIT" if was_cached else "MISS",
        "X-AIL-Hash": hash_value,
        "X-AIL-Tenant": tenant_id,
    }
    if duration:
        headers["X-AIL-Duration"] = str(duration)
    filename = f"{hash_value}.mp3"
    return FileResponse(
        mp3_path,
        media_type="audio/mpeg",
        filename=filename,
        headers=headers,
    )

# --- read
class ReadRequest(BaseModel):
    url: str | None = None
    text: str | None = None

# --- read
# ---- READ: fetch article → extract → prosody → stream (cached) ----
@app.post("/read")
async def read(req: ReadRequest, request: Request):
    tenant_id = get_validated_tenant(request, body=req)
    ensure_tenant_quota_ok(tenant_id, request=request)
    guard_request(request)
    if not (req.text or req.url):
        raise HTTPException(400, "Provide 'text' or 'url'")

    if req.url:
        if not is_public_http_url(req.url):
            raise HTTPException(400, "Invalid URL")

        client: httpx.AsyncClient = app.state.http_client
        r = await client.get(req.url, timeout=8, headers={"User-Agent": "Mozilla/5.0 (ReaderBot)"})
        if r.status_code != 200 or not r.text:
            raise HTTPException(502, "Fetch failed")

        extracted = trafilatura.extract(
            r.text, include_comments=False, include_tables=False, favor_precision=True
        )
        if not extracted:
            raise HTTPException(422, "No article content found")

        # title + author + cleaned body
        m = re.search(r"<title[^>]*>(.*?)</title>", r.text, flags=re.I | re.S)
        author = find_author_from_meta(r.text)
        title = (m.group(1).strip() if m else "")
        body = extracted.strip()
        tone = pick_tone(title, body)
        text = build_read_text(title, body, author)
        text, voice_settings = shape_text_for_tone(text, tone)
    else:
        tone = "neutral"
        text = prosody("", (req.text or ""))
        text, voice_settings = shape_text_for_tone(text, tone)

    # Demo cap for full reads
    if DEMO_MODE:
        text = text[:MAX_CHARS]
    # Use the shared cached streamer (disk + memory). This saves credits.
    usage_seconds = estimate_seconds_from_text(text)
    resp = await stream_tts_for_text(text, voice_id=VOICE_ID, model_id=MODEL_ID, voice_settings=voice_settings, tone=tone)
    if usage_seconds:
        record_tenant_usage_seconds(tenant_id, usage_seconds)
    return resp

@app.get("/read")
async def read(request: Request, url: str, voice: str | None = None, model: str | None = None):
    tenant_id = get_validated_tenant(request)
    ensure_tenant_quota_ok(tenant_id, request=request)
    title, author, text = extract_article(url)
    narration = prepare_article(title, author, text)
    # stream_tts_for_text is async and already returns a StreamingResponse
    usage_seconds = estimate_seconds_from_text(narration)
    resp = await stream_tts_for_text(
        narration,
        voice_id=voice or VOICE_ID,
        model_id=model or MODEL_ID,
    )
    if usage_seconds:
        record_tenant_usage_seconds(tenant_id, usage_seconds)
    return resp

@app.get("/read_chunked")
async def read_chunked(request: Request, url: str, voice: str | None = None, model: str | None = None):
    tenant_id = get_validated_tenant(request)
    ensure_tenant_quota_ok(tenant_id, request=request)
    # 1) Extract & prepare
    title, author, text = extract_article(url)
    cleaned = preprocess_for_tts(text or "")
    narration = prepare_article(title, author, cleaned)

    if not narration or len(narration.strip()) < 40:
        # Bail early with a clear error instead of sending empty 200
        raise HTTPException(status_code=422, detail="No narratable text extracted from page")

    parts = chunk_by_sentence(narration, target=1200, hard_max=1600)
    usage_seconds = estimate_seconds_from_text(narration)
    usage_recorded = False

    # 2) Prefetch-to-bytes for each chunk (safe and predictable)
    async def multi():
        nonlocal usage_recorded
        for i, part in enumerate(parts):
            try:
                processed_part = enhance_prosody(preprocess_for_tts(part))
                data = await tts_bytes(processed_part, voice or VOICE_ID, model or MODEL_ID)
                if usage_seconds and not usage_recorded:
                    record_tenant_usage_seconds(tenant_id, usage_seconds)
                    usage_recorded = True
                # yield the whole chunk as one piece (or slice into smaller pieces if you prefer)
                yield data
            except Exception as e:
                # Log and stop cleanly. Do NOT raise after streaming started.
                print({"event": "chunk_fail", "i": i, "err": str(e)[:300]})
                break

    return StreamingResponse(multi(), media_type="audio/mpeg", headers={"X-AIL-Tenant": tenant_id})


# _split_text_for_tts: reserved for future chunked synthesis


@app.get("/diag")
def diag():
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice = os.environ.get("ELEVENLABS_VOICE", "")
    return {
        "api_key_set": bool(key),
        "voice_set": bool(voice),
        "voice_prefix": (voice[:8] + "…") if voice else ""
    }

@app.get("/voices")
def voices():
    r = http.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": os.environ.get("ELEVENLABS_API_KEY","")},
        timeout=20,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()

@app.get("/tts_full")
def tts_full(
    request: Request,
    text: str = Query(..., max_length=20000),
    voice: str | None = Query(None),
    model: str = Query("eleven_turbo_v2"),
    stability: float = Query(0.35),
    similarity: float = Query(0.75),
    style: float = Query(0.40),
    speaker_boost: bool = Query(True),
):
    tenant_id = get_validated_tenant(request)
    ensure_tenant_quota_ok(tenant_id, request=request)
    voice = voice or os.environ.get("ELEVENLABS_VOICE", "")
    if not voice:
        raise HTTPException(status_code=400, detail="Voice not provided.")
    clean = preprocess_for_tts(text)
    usage_seconds = estimate_seconds_from_text(clean)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
    headers = {
        "xi-api-key": os.environ.get("ELEVENLABS_API_KEY",""),
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    payload = {
        "text": clean,
        "model_id": model,
        "voice_settings": {
            "stability": float(stability),
            "similarity_boost": float(similarity),
            "style": float(style),
            "use_speaker_boost": bool(speaker_boost),
        },
    }
    r = http.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    if usage_seconds:
        record_tenant_usage_seconds(tenant_id, usage_seconds)
    return Response(content=r.content, media_type="audio/mpeg")


TEMPLATE = Path("static/demo-shell.html")  # <- uses your exact index.html shell

@app.get("/demo", response_class=HTMLResponse)
async def demo(url: str):
    # fetch page
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            r.raise_for_status()
        raw = r.text
    except Exception as e:
        return HTMLResponse(f"<h1>Fetch error</h1><pre>{escape(str(e))}</pre>", status_code=502)

    # extract body + title
    meta = trafilatura.bare_extraction(raw) or {}
    title = escape(meta.get("title") or "Demo Article")
    body  = trafilatura.extract(raw, include_comments=False, include_images=False) \
           or "<p>No article content extracted.</p>"

    # load your shell and inject content
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("{{TITLE}}", title).replace("{{ARTICLE}}", body)

    return HTMLResponse(html, status_code=200)
