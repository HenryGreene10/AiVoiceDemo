import os
import time
import hmac
import hashlib
import base64
import json
from typing import Optional

import boto3
import httpx
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mangum import Mangum

from security import (
    allowed_origins_set,
    issue_token,
    verify_token,
)
from storage import (
    get_bucket_name,
    exists as s3_exists,
    put_audio,
    get_audio_url,
    current_cache_bytes,
    reap_lru_if_needed,
)
from prosody import shape_text_for_tone, sentiment_from_title
from metrics import append_stream_row

try:
    import trafilatura
except Exception:  # pragma: no cover
    trafilatura = None


# --- env / config
REGION = os.getenv("REGION", os.getenv("AWS_REGION", "us-east-1"))
S3_BUCKET = os.getenv("S3_BUCKET", "")
MODEL_ID_DEFAULT = os.getenv("MODEL_ID", "eleven_flash_v2_5")
VOICE_ID_DEFAULT = os.getenv("VOICE_ID", "default")
MAX_CHARS = int(os.getenv("MAX_CHARS", "2800"))
MAX_CACHE_BYTES = int(os.getenv("MAX_CACHE_BYTES", "2000000000"))
SECRETS_ELEVEN_KEY_NAME = os.getenv("ELEVENLABS_SECRET_NAME", "ELEVENLABS_API_KEY")


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(allowed_origins_set()) if allowed_origins_set() else ["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)


# --- secrets (cached on cold start)
_ELEVEN_API_KEY: Optional[str] = None


def get_eleven_api_key() -> str:
    global _ELEVEN_API_KEY
    if _ELEVEN_API_KEY:
        return _ELEVEN_API_KEY
    # Try env first for local/dev
    env_key = os.getenv("ELEVENLABS_API_KEY")
    if env_key:
        _ELEVEN_API_KEY = env_key
        return _ELEVEN_API_KEY
    # Fallback to Secrets Manager
    sm = boto3.client("secretsmanager", region_name=REGION)
    resp = sm.get_secret_value(SecretId=SECRETS_ELEVEN_KEY_NAME)
    val = resp.get("SecretString") or resp.get("SecretBinary")
    if isinstance(val, (bytes, bytearray)):
        val = val.decode("utf-8", errors="ignore")
    if not val:
        raise RuntimeError("Missing ELEVENLABS_API_KEY secret")
    _ELEVEN_API_KEY = val.strip()
    return _ELEVEN_API_KEY


# Shared HTTP client for better cold/warm perf
_http_client: Optional[httpx.AsyncClient] = None


async def get_http() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    return _http_client


@app.get("/health")
def health():
    return {"ok": True}


class TokenReq(BaseModel):
    origin: str
    path: str
    ttl_seconds: int | None = 300


@app.post("/sdk/token")
def sdk_token(req: TokenReq):
    origins = allowed_origins_set()
    if origins and req.origin not in origins:
        raise HTTPException(403, "Origin not allowed")
    ttl = int(req.ttl_seconds or 300)
    exp_ts = int(time.time()) + min(max(ttl, 60), 600)
    tok = issue_token(req.origin, req.path, exp_ts)
    return {"token": tok, "exp": exp_ts}


def _require_origin_and_token(request: Request):
    # Dev bypass
    if (os.getenv("DEV_BYPASS_TOKEN", "").strip().lower() in ("1","true","yes")):
        return request.headers.get("origin") or request.headers.get("Origin") or ""
    origin = request.headers.get("origin") or request.headers.get("Origin")
    if not origin:
        raise HTTPException(400, "Missing Origin header")
    origins = allowed_origins_set()
    if origins and origin not in origins:
        raise HTTPException(403, "Origin not allowed")
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Missing token")
    token = auth.split(" ", 1)[1].strip()
    # Path binding: use the path being called for tight scope
    path = request.url.path
    if not verify_token(token, origin, path):
        raise HTTPException(401, "Invalid/expired token")
    return origin


class SynthReq(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None
    voiceId: Optional[str] = None
    modelId: Optional[str] = None
    tone: Optional[str] = None  # "neutral"|"sober"|"upbeat"


def _compute_cache_key(model_id: str, voice_id: str, tone: str, text: str) -> str:
    h = hashlib.sha1(f"{model_id}|{voice_id}|{tone}|{hashlib.sha1(text.encode('utf-8')).hexdigest()}".encode("utf-8")).hexdigest()
    return h


async def _extract_from_url(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    r = await client.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (ReaderBot)"})
    if r.status_code != 200 or not r.text:
        raise HTTPException(502, "Fetch failed")
    html = r.text
    title = ""
    try:
        import re
        m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
        if m:
            title = (m.group(1) or "").strip()
    except Exception:
        pass
    body = ""
    if trafilatura is not None:
        extracted = trafilatura.extract(html, include_comments=False, include_tables=False, favor_precision=True)
        body = (extracted or "").strip()
    if not body:
        raise HTTPException(422, "No article content found")
    return title, body


async def _synthesize_to_s3(text: str, voice_id: str, model_id: str, tone: str) -> bytes:
    prepared_text, voice_settings = shape_text_for_tone(text, tone)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {
        "xi-api-key": get_eleven_api_key(),
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    payload = {
        "text": prepared_text,
        "model_id": model_id,
        "voice_settings": voice_settings,
        "optimize_streaming_latency": 2,
        "apply_text_normalization": False,
    }
    client = await get_http()
    total = 0
    buf = bytearray()
    async with client.stream("POST", url, headers=headers, json=payload) as resp:
        if resp.status_code != 200:
            detail = await resp.aread()
            raise HTTPException(502, f"TTS error {resp.status_code}")
        async for chunk in resp.aiter_bytes():
            if not chunk:
                continue
            total += len(chunk)
            buf.extend(chunk)
    return bytes(buf)


@app.post("/synthesize")
async def synthesize(req: SynthReq, request: Request):
    _require_origin_and_token(request)

    model_id = (req.modelId or MODEL_ID_DEFAULT).strip()
    voice_id = (req.voiceId or VOICE_ID_DEFAULT).strip()
    tone = (req.tone or "neutral").strip().lower()

    if not (req.text or req.url):
        raise HTTPException(400, "Provide 'text' or 'url'")

    client = await get_http()
    if req.url:
        title, body = await _extract_from_url(client, req.url)
        if tone == "auto" or tone not in {"neutral", "sober", "upbeat"}:
            tone = sentiment_from_title(title)
        # Simple intro/outro
        text = (f"Now reading: {title}.\n\n" if title else "") + body
    else:
        text = req.text or ""

    text = text.strip()
    if not text:
        raise HTTPException(400, "Empty text")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]

    cache_key = _compute_cache_key(model_id, voice_id, tone, text)
    if await s3_exists(cache_key):
        url = await get_audio_url(cache_key)
        append_stream_row(int(time.time() * 1000), "hit", 0, 0, model_id, cache_key)
        return {"audioUrl": url, "cache": "hit"}

    # Miss: synthesize, upload, metric, reaper
    start = time.time()
    audio_bytes = await _synthesize_to_s3(text, voice_id, model_id, tone)
    first_ms = int((time.time() - start) * 1000)
    await put_audio(cache_key, audio_bytes)
    url = await get_audio_url(cache_key)
    append_stream_row(int(time.time() * 1000), "api", first_ms, len(audio_bytes), model_id, cache_key)

    # background-like cleanup (best-effort)
    try:
        await reap_lru_if_needed()
    except Exception:
        pass

    return {"audioUrl": url, "cache": "miss"}


# Lambda entrypoint
handler = Mangum(app)


