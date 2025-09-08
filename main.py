# main.py
import os, hashlib, requests, time, httpx
from pathlib import Path
from collections import OrderedDict
from dotenv import load_dotenv; 
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import Response, StreamingResponse, JSONResponse, FileResponse, PlainTextResponse, HTMLResponse
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi import Query, Body
import trafilatura, re, requests as http, json
from html import escape
from trafilatura.metadata import extract_metadata
from typing import Tuple, Optional
from urllib.parse import urlparse, quote
import socket, ipaddress, asyncio, json
import re
from fastapi.staticfiles import StaticFiles
import csv
from threading import Lock
from datetime import datetime, timezone

# --- tenant key authentication ---
TENANT_KEYS = set(s.strip() for s in os.getenv("TENANT_KEYS","").split(",") if s.strip())

async def require_tenant(request: Request):
    if not TENANT_KEYS:
        return  # open mode
    key = request.headers.get("x-tenant-key")
    if key not in TENANT_KEYS:
        raise HTTPException(status_code=401, detail="Missing or invalid tenant key.")

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

def rate_limit_check(request: Request):
    ip = _client_ip(request)
    ok_ip = _allow(_ip_hits, ip, *RATE_LIMITS["per_ip"])
    # tenant key (or 'public' if open mode)
    tenant = request.headers.get("x-tenant-key") or "public"
    ok_tenant = _allow(_tenant_hits, tenant, *RATE_LIMITS["per_tenant"])
    if not (ok_ip and ok_tenant):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please retry later.")
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
from pathlib import Path
CACHE_DIR = Path(os.getenv("CACHE_DIR","cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes")
MAX_CHARS = 1600  # ~90 seconds
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
STUB_TTS = os.getenv("STUB_TTS", "0").strip().lower() in ("1","true","yes")
OPT_LATENCY = int(os.getenv("OPT_LATENCY", "0").strip())  # was 2; 0 = safest with ElevenLabs


# --- app
app = FastAPI()

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
            "stability": 0.35,
            "similarity_boost": 0.9,
            "style": 0.35,
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
async def read_chunked(url: str, voice: str | None = None, model: str | None = None):
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

    # 2) PREFETCH FIRST CHUNK to avoid 200/0B
    try:
        first_bytes = await tts_bytes(parts[0], v, m)
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
                data = await tts_bytes(part, v, m)
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
    ALLOWED = ["http://127.0.0.1:8000","http://localhost:8000"]

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
async def read_chunked(url: str, voice: str | None = None, model: str | None = None):
    title, author, text = extract_article(url)
    narration = prepare_article(title, author, preprocess_for_tts(text))
    parts = chunk_by_sentence(narration, target=1200, hard_max=1600)

    async def multi():
        for i, part in enumerate(parts):
            try:
                async for b in stream_bytes_for_text_safe(
                    part, voice or VOICE_ID, model or MODEL_ID
                ):
                    if b:
                        yield b
            except Exception as e:
                # Log, then stop or continue; do NOT raise after streaming started
                print({"event": "chunk_fail", "i": i, "err": str(e)[:200]})
                break  # or `continue` to try next part

    return StreamingResponse(multi(), media_type="audio/mpeg")






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

# --- analytics CSV tracking ---
ANALYTICS_CSV = (CACHE_DIR / "analytics.csv").resolve()
_analytics_lock = Lock()

class MetricReq(BaseModel):
    event: str            # "click"|"start"|"stop"|"progress"|"ended"
    seconds: float = 0.0  # for ended / stop
    url: Optional[str] = None
    voice: Optional[str] = None
    tenant: Optional[str] = None
    user_agent: Optional[str] = None

@app.post("/metric")
def metric(req: MetricReq, request: Request, x_tenant_key: Optional[str] = Header(default=None)):
    row = [
        int(time.time()),
        req.event,
        round(float(req.seconds or 0), 2),
        req.url or str(request.headers.get("referer", "")),
        req.voice or os.getenv("VOICE_ID",""),
        (req.tenant or x_tenant_key or ""),
        request.client.host,
        request.headers.get("user-agent","")
    ]
    with _analytics_lock:
        new_file = not ANALYTICS_CSV.exists()
        with ANALYTICS_CSV.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["ts","event","seconds","url","voice","tenant","ip","ua"])
            w.writerow(row)
    return {"ok": True}

@app.get("/admin/analytics.csv")
def analytics_csv():
    if ANALYTICS_CSV.exists():
        return FileResponse(str(ANALYTICS_CSV), media_type="text/csv", filename="analytics.csv")
    raise HTTPException(404, "no analytics yet")

# (Optional) filter by tenant or since timestamp
@app.get("/admin/analytics.json")
def analytics_summary(tenant: Optional[str] = None, since_ts: Optional[int] = None):
    out = {
        "total_impressions": 0,
        "total_clicks": 0,
        "total_seconds": 0.0,
        "by_url": {},
        "by_tenant": {}
    }
    if not ANALYTICS_CSV.exists():
        return out

    with ANALYTICS_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try: ts = int(r.get("ts") or 0)
            except: ts = 0
            if since_ts and ts < since_ts:
                continue
            if tenant and (r.get("tenant") or "") != tenant:
                continue

            ev = (r.get("event") or "").lower()
            secs = float(r.get("seconds") or 0)
            url  = r.get("url") or ""
            tnt  = r.get("tenant") or ""

            if ev == "impression": out["total_impressions"] += 1
            if ev == "click":       out["total_clicks"] += 1
            if ev in ("ended","stop"): out["total_seconds"] += secs

            if url:
                b = out["by_url"].setdefault(url, {"impressions":0,"clicks":0,"seconds":0.0})
                if ev == "impression": b["impressions"] += 1
                if ev == "click":       b["clicks"] += 1
                if ev in ("ended","stop"): b["seconds"] += secs

            if tnt:
                t = out["by_tenant"].setdefault(tnt, {"impressions":0,"clicks":0,"seconds":0.0})
                if ev == "impression": t["impressions"] += 1
                if ev == "click":       t["clicks"] += 1
                if ev in ("ended","stop"): t["seconds"] += secs

    out["total_seconds"] = round(out["total_seconds"], 2)
    # compute CTRs
    for d in (out["by_url"].values(), out["by_tenant"].values()):
        for v in d:
            pass
    return out

@app.get("/admin/analytics_timeseries.json")
def analytics_timeseries(days: int = 30, tenant: Optional[str] = None):
    """Return last N days of clicks & seconds (UTC date buckets)."""
    if not ANALYTICS_CSV.exists():
        return {"days": [], "clicks": [], "seconds": []}

    # build buckets
    today = datetime.now(timezone.utc).date()
    order = [str(today.fromordinal(today.toordinal()-i)) for i in range(days)][::-1]
    clicks = {d:0 for d in order}
    seconds = {d:0.0 for d in order}

    with ANALYTICS_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if tenant and (r.get("tenant") or "") != tenant:
                continue
            try:
                ts = int(r.get("ts") or 0)
                d = datetime.fromtimestamp(ts, timezone.utc).date()
                key = str(d)
            except:
                continue
            if key not in clicks:  # out of range
                continue

            ev = (r.get("event") or "").lower()
            secs = float(r.get("seconds") or 0)
            if ev == "click": clicks[key] += 1
            if ev in ("ended","stop"): seconds[key] += secs

    return {
        "days": order,
        "clicks": [clicks[d] for d in order],
        "seconds": [round(seconds[d],2) for d in order],
    }

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
    await require_tenant(request)
    rate_limit_check(request)
    v = voice or os.environ.get("ELEVENLABS_VOICE") or os.environ.get("VOICE_ID") or ""
    if not v:
        raise HTTPException(status_code=400, detail="Voice not provided (and ELEVENLABS_VOICE/VOICE_ID not set).")
    return stream_with_cache(text, v, model or MODEL_ID, stability, similarity, style, speaker_boost, opt_latency)

@app.post("/tts")
def tts_post(
    body: TTSBody,
    voice: str | None = Query(None),
    model: str | None = Query(None),
    stability: float = Query(0.35),
    similarity: float = Query(0.9),
    style: float = Query(0.35),
    speaker_boost: bool = Query(True),
    opt_latency: int = Query(2),
):
    v = voice or os.environ.get("ELEVENLABS_VOICE") or os.environ.get("VOICE_ID") or ""
    if not v:
        raise HTTPException(status_code=400, detail="Voice not provided (and ELEVENLABS_VOICE/VOICE_ID not set).")
    return stream_with_cache(body.text, v, model or MODEL_ID, stability, similarity, style, speaker_boost, opt_latency)

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
    await require_tenant(request)
    rate_limit_check(request)

    v = (voice or os.environ.get("ELEVENLABS_VOICE") or os.environ.get("VOICE_ID") or "").strip()
    if not v:
        raise HTTPException(400, "Voice not provided (and ELEVENLABS_VOICE/VOICE_ID not set).")

    # Normalize and (optionally) cap for safety
    clean = preprocess_for_tts(body.text or "")[:600]

    key  = _cache_key(clean, v, (model or MODEL_ID), stability, similarity, style, speaker_boost, opt_latency)
    outp = _mp3_path(key)

    # If file exists & non-empty -> HIT
    if outp.exists() and outp.stat().st_size > 0:
        return {"audioUrl": public_url(f"/cache/{outp.name}"), "hit": True}

    # MISS: debounce by key so duplicate clicks don't double-spend
    lock = get_lock(key)
    async with lock:
        # re-check after awaiting
        if outp.exists() and outp.stat().st_size > 0:
            return {"audioUrl": public_url(f"/cache/{outp.name}"), "hit": True}

        try:
            data = await tts_bytes(clean, v, (model or MODEL_ID))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Provider error: {e}")

        tmp = outp.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(outp)

    return {"audioUrl": public_url(f"/cache/{outp.name}"), "hit": False}

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
    return {
        "has_api_key": bool(key),
        "api_key_head": (key[:4] + "…" if key else None),
        "voice_id": VOICE_ID,
        "model_id": MODEL_ID,
    }


@app.get("/read")
async def read(url: str, voice: str | None = None, model: str | None = None):
    # sanity: key/voice present
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
            audio = await tts_bytes(part, v, m)
            bufs.append(audio)
            print({"event":"read_part_ok","i":i,"bytes":len(audio)})
        except Exception as e:
            # stop cleanly; we'll still return what we have
            print({"event":"read_part_fail","i":i,"err":str(e)[:300]})
            break

    merged = b"".join(bufs)
    if not merged:
        raise HTTPException(status_code=502, detail="Upstream produced no audio for any chunk")

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
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": voice_settings or {
            "stability": 0.35, "similarity_boost": 0.9, "style": 0.35, "use_speaker_boost": True,
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
                      speaker_boost: bool, opt_latency: int):
    """
    Streams TTS audio from ElevenLabs, with:
      - preflight status check (no streaming starts if upstream is an error)
      - first-chunk prefetch (we have a chunk before returning StreamingResponse)
      - never-raise-after-yield (avoid 'response already started' runtime error)
      - write-through cache with budget eviction
    """
    metrics["tts_requests"] += 1
    clean = preprocess_for_tts(text)

    key  = _cache_key(clean, voice, model, stability, similarity, style, speaker_boost, opt_latency)
    path = os.path.join(CACHE_DIR, f"{key}.mp3")
    if os.path.exists(path):
        metrics["tts_cache_hits"] += 1
        write_stream_row(int(time.time()*1000), "HIT", 0, os.path.getsize(path), model, os.path.basename(path).split(".")[0])
        return FileResponse(path, media_type="audio/mpeg", headers={"X-Cache": "HIT"})

    metrics["tts_cache_misses"] += 1

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream"
    headers = {
        "xi-api-key": os.environ.get("ELEVENLABS_API_KEY", ""),
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    payload = {
        "text": clean,
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
async def precache_text(req: PrecacheReq, x_tenant_key: Optional[str] = Header(default=None)):
    # optional: enforce tenant like other endpoints
    # if TENANT_KEYS and x_tenant_key not in TENANT_KEYS: raise HTTPException(401, "bad tenant")
    voice = req.voice or os.getenv("VOICE_ID", "")
    if not req.text.strip():
        raise HTTPException(400, "text required")
    key = _cache_key_simple(req.text, voice)
    outp = _mp3_path(key)
    created = False
    with _precache_lock:
        if not outp.exists():
            # synth_to_file should call ElevenLabs and write MP3 to outp
            url = await elevenlabs_tts_to_file(req.text, voice, outp)  # <-- use your existing function name
            created = True
    return {"ok": True, "created": created, "audioUrl": f"/cache/{outp.name}"}

@app.get("/precache_status")
def precache_status(text: str, voice: Optional[str] = None):
    voice = voice or os.getenv("VOICE_ID", "")
    key = _cache_key_simple(text, voice)
    outp = _mp3_path(key)
    return {"ok": True, "exists": outp.exists(), "audioUrl": f"/cache/{outp.name}" if outp.exists() else None}

def stream_with_cache(text: str, voice: str, model: str,
                      stability: float, similarity: float, style: float,
                      speaker_boost: bool, opt_latency: int):
    metrics["tts_requests"] += 1
    clean = preprocess_for_tts(text)

    key  = _cache_key(clean, voice, model, stability, similarity, style, speaker_boost, opt_latency)
    path = os.path.join(CACHE_DIR, f"{key}.mp3")
    if os.path.exists(path):
        metrics["tts_cache_hits"] += 1
        write_stream_row(int(time.time()*1000), "HIT", 0, os.path.getsize(path), model, os.path.basename(path).split(".")[0])
        return FileResponse(path, media_type="audio/mpeg", headers={"X-Cache": "HIT"})

    metrics["tts_cache_misses"] += 1

    # ----- preflight (no bytes sent to client yet)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream"
    headers = {
        "xi-api-key": os.environ.get("ELEVENLABS_API_KEY", ""),
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    payload = {
        "text": clean,
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

    # Prefetch first chunk before starting response
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
                f.write(first_chunk);  yield first_chunk
                for c in chunk_iter:
                    if not c: continue
                    f.write(c);         yield c
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
        except Exception:
            try:
                if not complete and os.path.exists(tmp):
                    os.remove(tmp)
            except:
                pass
            return  # do NOT raise once streaming has begun

    return StreamingResponse(gen(), media_type="audio/mpeg", headers={"X-Cache": "MISS"})


@app.get("/cache/stats")
def cache_stats():
    s = get_cache_stats()
    return {**s, "hits": metrics["tts_cache_hits"], "misses": metrics["tts_cache_misses"]}

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

# --- TTS request (streaming via shared function)
@app.post("/tts")
async def tts(req: TTSRequest, request: Request):
    guard_request(request)
    sample_text = (
        "This is a short sample paragraph to verify streaming text to speech. "
        "Audio should begin quickly and continue without interruption."
    )
    text = (getattr(req, "text", "") or "").strip() or sample_text
    return await stream_tts_for_text(text, voice_id=VOICE_ID, model_id=MODEL_ID)

# --- TTS GET for direct <audio src>
@app.get("/tts")
def tts(
    text: str = Query(..., max_length=20000),
    voice: str | None = Query(None),
    model: str = Query("eleven_turbo_v2"),
    stability: float = Query(0.35),
    similarity: float = Query(0.75),
    style: float = Query(0.40),
    speaker_boost: bool = Query(True),
    opt_latency: int = Query(2),
):
    voice = voice or os.environ.get("ELEVENLABS_VOICE", "")
    if not voice:
        raise HTTPException(status_code=400, detail="Voice not provided (and ELEVENLABS_VOICE not set).")
    return stream_with_cache(text, voice, model, stability, similarity, style, speaker_boost, opt_latency)

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

# --- read
class ReadRequest(BaseModel):
    url: str | None = None
    text: str | None = None

# --- read
# ---- READ: fetch article → extract → prosody → stream (cached) ----
@app.post("/read")
async def read(req: ReadRequest, request: Request):
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
    return await stream_tts_for_text(text, voice_id=VOICE_ID, model_id=MODEL_ID, voice_settings=voice_settings, tone=tone)

@app.get("/read")
async def read(url: str, voice: str | None = None, model: str | None = None):
    title, author, text = extract_article(url)
    narration = prepare_article(title, author, text)
    # stream_tts_for_text is async and already returns a StreamingResponse
    return await stream_tts_for_text(
        narration,
        voice_id=voice or VOICE_ID,
        model_id=model or MODEL_ID,
    )

@app.get("/read_chunked")
async def read_chunked(url: str, voice: str | None = None, model: str | None = None):
    # 1) Extract & prepare
    title, author, text = extract_article(url)
    cleaned = preprocess_for_tts(text or "")
    narration = prepare_article(title, author, cleaned)

    if not narration or len(narration.strip()) < 40:
        # Bail early with a clear error instead of sending empty 200
        raise HTTPException(status_code=422, detail="No narratable text extracted from page")

    parts = chunk_by_sentence(narration, target=1200, hard_max=1600)

    # 2) Prefetch-to-bytes for each chunk (safe and predictable)
    async def multi():
        for i, part in enumerate(parts):
            try:
                data = await tts_bytes(part, voice or VOICE_ID, model or MODEL_ID)
                # yield the whole chunk as one piece (or slice into smaller pieces if you prefer)
                yield data
            except Exception as e:
                # Log and stop cleanly. Do NOT raise after streaming started.
                print({"event": "chunk_fail", "i": i, "err": str(e)[:300]})
                break

    return StreamingResponse(multi(), media_type="audio/mpeg")


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
    text: str = Query(..., max_length=20000),
    voice: str | None = Query(None),
    model: str = Query("eleven_turbo_v2"),
    stability: float = Query(0.35),
    similarity: float = Query(0.75),
    style: float = Query(0.40),
    speaker_boost: bool = Query(True),
):
    voice = voice or os.environ.get("ELEVENLABS_VOICE", "")
    if not voice:
        raise HTTPException(status_code=400, detail="Voice not provided.")
    clean = preprocess_for_tts(text)
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
