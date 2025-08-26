# main.py
import os, hashlib, requests, time, httpx
from pathlib import Path
from collections import OrderedDict
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi import Query
import trafilatura, re, requests as http
from urllib.parse import urlparse, quote
import socket, ipaddress, asyncio, json
from fastapi.staticfiles import StaticFiles
from metrics import write_stream_row

# --- config / env
load_dotenv(".env")
API_KEY = os.getenv("ELEVENLABS_API_KEY")
assert API_KEY, "Set ELEVENLABS_API_KEY in .env"
VOICE_ID = "EQu48Nbp4OqDxsnYh27f"  # your default voice
MODEL_ID = "eleven_turbo_v2"
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes")
MAX_CHARS = 1600  # ~90 seconds
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()

# --- app
app = FastAPI()

ALLOW_ORIGINS = os.getenv("ALLOW_ORIGINS", "").strip()
ALLOWED_ORIGINS_SET = set([o.strip() for o in ALLOW_ORIGINS.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # dev only; lock down later
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# keep a single async HTTP client alive for connection reuse (lower TTFB)
@app.on_event("startup")
async def _startup():
    app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    app.state.locks = {}

@app.on_event("shutdown")
async def _shutdown():
    await app.state.http_client.aclose()

# --- simple PNA preflight helper (FastAPI's CORS doesn't add this header yet)
@app.options("/{path:path}")
async def preflight(req: Request, path: str):
    headers = {
        "Access-Control-Allow-Origin": req.headers.get("origin", "*") if ALLOWED_ORIGINS_SET else "*",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Private-Network": "true",
    }
    return Response(status_code=204, headers=headers)

# --- health check
@app.get("/health")
def health():
    return {"ok": True}

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

# --- metric (very simple)
@app.post("/metric")
async def metric(req: Request):
    try:
        data = await req.json()
    except Exception:
        data = {"raw": (await req.body()).decode(errors="ignore")[:500]}
    print({"event":"metric", **data})
    return {"ok": True}

# --- simple API key guard (prod only)
ALLOWED_KEYS = set([k.strip() for k in os.getenv("ALLOWED_KEYS", "").split(",") if k.strip()])

def dev_bypass_enabled():
    return os.getenv("DEV_BYPASS_TOKEN", "").strip().lower() in ("1","true","yes")

def guard_request(req: Request):
    if dev_bypass_enabled():
        return
    if not DEMO_MODE:
        origin = req.headers.get("origin")
        if ALLOWED_ORIGINS_SET and origin not in ALLOWED_ORIGINS_SET:
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

async def stream_tts_for_text(text: str, voice_id: str = VOICE_ID, model_id: str = MODEL_ID, voice_settings: dict | None = None, tone: str = "neutral"):
    """Stream audio; write to disk cache; return StreamingResponse."""
    client: httpx.AsyncClient = app.state.http_client
    h = tts_hash(text, voice_id, model_id)
    print({"event":"hash_debug","hash":h,"text_head":text[:80]})
    p = cache_path(h)

    # memory cache
    if h in cache:
        print({"event":"cache_hit_mem","hash":h})
        try:
            write_stream_row(int(time.time()*1000), "mem", 0, len(cache[h]), model_id, h)
        except Exception:
            pass
        return Response(content=cache[h], media_type="audio/mpeg", headers={"x-cache-hit": "true"})
    # disk cache
    if p.exists():
        size = p.stat().st_size
        print({"event":"cache_hit_disk","hash":h,"bytes":size})
        data = p.read_bytes()
        cache.put(h, data)
        try:
            write_stream_row(int(time.time()*1000), "disk", 0, size, model_id, h)
        except Exception:
            pass
        return Response(content=data, media_type="audio/mpeg", headers={"x-cache-hit": "true"})

    lock = get_lock(h)
    async with lock:
        if h in cache:
            return Response(content=cache[h], media_type="audio/mpeg", headers={"x-cache-hit": "true"})
        if p.exists():
            data = p.read_bytes()
            cache.put(h, data)
            return Response(content=data, media_type="audio/mpeg", headers={"x-cache-hit": "true"})

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        headers = {
            "xi-api-key": API_KEY,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        }
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

        start_time = time.time()
        first_chunk_time = None
        total_bytes = 0
        buf = bytearray()
        tmp_path = p.with_suffix(".part")

        async def gen():
            nonlocal first_chunk_time, total_bytes
            try:
                with tmp_path.open("wb") as f:
                    print({"event": "tts_api_call", "hash": h, "model": model_id})
                    async with client.stream("POST", url, headers=headers, json=payload) as resp:
                        if resp.status_code != 200:
                            err = await resp.aread()
                            print({"event":"tts_error","status":resp.status_code,"detail":err[:200]})
                            return
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
async def tts_get(text: str = Query("", min_length=0), model: str = Query(MODEL_ID), request: Request = None):
    if request is not None:
        guard_request(request)
    return await stream_tts_for_text(text or "Hello", voice_id=VOICE_ID, model_id=model)

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

# GET /read — used by the inline <audio> player
@app.get("/read")
async def read_get(url: str | None = Query(None, min_length=8), text: str | None = None, request: Request = None):
    if request is not None:
        guard_request(request)
    if not (url or text):
        raise HTTPException(400, "Provide 'text' or 'url'")

    if url:
        if not is_public_http_url(url):
            raise HTTPException(400, "Invalid URL")

        client: httpx.AsyncClient = app.state.http_client
        r = await client.get(url, timeout=8, headers={"User-Agent":"Mozilla/5.0 (ReaderBot)"})
        if r.status_code != 200 or not r.text:
            raise HTTPException(502, "Fetch failed")

        extracted = trafilatura.extract(
            r.text, include_comments=False, include_tables=False, favor_precision=True
        )
        if not extracted:
            raise HTTPException(422, "No article content found")

        m = re.search(r"<title[^>]*>(.*?)</title>", r.text, flags=re.I | re.S)
        title = (m.group(1).strip() if m else "")
        author = find_author_from_meta(r.text)
        body  = extracted.strip()
        tone = pick_tone(title, body)
        text_final = build_read_text(title, body, author)
        text_final, voice_settings = shape_text_for_tone(text_final, tone)
    else:
        tone = "neutral"
        text_final = prosody("", text or "")
        text_final, voice_settings = shape_text_for_tone(text_final, tone)

    # Demo cap for full reads
    if DEMO_MODE:
        text_final = text_final[:MAX_CHARS]
    return await stream_tts_for_text(text_final, voice_id=VOICE_ID, model_id=MODEL_ID, voice_settings=voice_settings, tone=tone)


# _split_text_for_tts: reserved for future chunked synthesis

