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

# --- app
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
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
async def preflight(_: Request, path: str):
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Private-Network": "true",
    }
    return Response(status_code=204, headers=headers)

# --- health check
@app.get("/health")
def health():
    return {"ok": True}

# --- metric (very simple)
@app.post("/metric")
async def metric(req: Request):
    try:
        data = await req.json()
    except Exception:
        data = {"raw": (await req.body()).decode(errors="ignore")[:500]}
    print({"event":"metric", **data})
    return {"ok": True}

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

async def stream_tts_for_text(text: str, voice_id: str = VOICE_ID, model_id: str = MODEL_ID):
    """Stream audio; write to disk cache; return StreamingResponse."""
    client: httpx.AsyncClient = app.state.http_client
    h = tts_hash(text, voice_id, model_id)
    print({"event":"hash_debug","hash":h,"text_head":text[:80]})
    p = cache_path(h)

    # memory cache
    if h in cache:
        print({"event":"cache_hit_mem","hash":h})
        return Response(content=cache[h], media_type="audio/mpeg")
    # disk cache
    if p.exists():
        print({"event":"cache_hit_disk","hash":h,"bytes":p.stat().st_size})
        data = p.read_bytes()
        cache.put(h, data)
        return Response(content=data, media_type="audio/mpeg")

    lock = get_lock(h)
    async with lock:
        if h in cache:
            return Response(content=cache[h], media_type="audio/mpeg")
        if p.exists():
            data = p.read_bytes()
            cache.put(h, data)
            return Response(content=data, media_type="audio/mpeg")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        headers = {
            "xi-api-key": API_KEY,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
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
                print({
                    "event": "tts_stream",
                    "first_audio_ms": int(((first_chunk_time or time.time()) - start_time) * 1000),
                    "total_bytes": total_bytes,
                    "hash": h,
                })
                if total_bytes > 0:
                    try:
                        tmp_path.replace(p)
                        cache.put(h, bytes(buf))
                    except Exception as e:
                        print({"event":"cache_finalize_error","err":str(e)})

        return StreamingResponse(gen(), media_type="audio/mpeg")

# --- TTS request (streaming via shared function)
@app.post("/tts")
async def tts(req: TTSRequest):
    sample_text = (
        "This is a short sample paragraph to verify streaming text to speech. "
        "Audio should begin quickly and continue without interruption."
    )
    text = (getattr(req, "text", "") or "").strip() or sample_text
    return await stream_tts_for_text(text, voice_id=VOICE_ID, model_id=MODEL_ID)

# --- TTS GET for direct <audio src>
@app.get("/tts")
async def tts_get(text: str = Query("", min_length=0), model: str = Query(MODEL_ID)):
    return await stream_tts_for_text(text or "Hello", voice_id=VOICE_ID, model_id=model)

# --- extract
@app.get("/extract")
def extract(url: str = Query(..., min_length=8)):
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

# --- read
class ReadRequest(BaseModel):
    url: str | None = None
    text: str | None = None

# --- read
# ---- READ: fetch article → extract → prosody → stream (cached) ----
@app.post("/read")
async def read(req: ReadRequest):
    if not (req.text or req.url):
        raise HTTPException(400, "Provide 'text' or 'url'")

    if req.url:
        if not is_public_http_url(req.url):
            raise HTTPException(400, "Invalid URL")

        r = http.get(req.url, timeout=8, headers={"User-Agent": "Mozilla/5.0 (ReaderBot)"})
        if r.status_code != 200 or not r.text:
            raise HTTPException(502, "Fetch failed")

        extracted = trafilatura.extract(
            r.text, include_comments=False, include_tables=False, favor_precision=True
        )
        if not extracted:
            raise HTTPException(422, "No article content found")

        # title from HTML <title> (simple fallback)
        m = re.search(r"<title[^>]*>(.*?)</title>", r.text, flags=re.I | re.S)
        title = (m.group(1).strip() if m else "")
        body = extracted.strip()
        text = prosody(title, body)
    else:
        text = prosody("", (req.text or ""))

    # Demo cap for full reads
    if DEMO_MODE:
        text = text[:MAX_CHARS]
    # Use the shared cached streamer (disk + memory). This saves credits.
    return await stream_tts_for_text(text, voice_id=VOICE_ID, model_id=MODEL_ID)

# GET /read — used by the inline <audio> player
@app.get("/read")
async def read_get(url: str | None = Query(None, min_length=8), text: str | None = None):
    if not (url or text):
        raise HTTPException(400, "Provide 'text' or 'url'")

    if url:
        if not is_public_http_url(url):
            raise HTTPException(400, "Invalid URL")

        r = http.get(url, timeout=8, headers={"User-Agent":"Mozilla/5.0 (ReaderBot)"})
        if r.status_code != 200 or not r.text:
            raise HTTPException(502, "Fetch failed")

        extracted = trafilatura.extract(
            r.text, include_comments=False, include_tables=False, favor_precision=True
        )
        if not extracted:
            raise HTTPException(422, "No article content found")

        m = re.search(r"<title[^>]*>(.*?)</title>", r.text, flags=re.I | re.S)
        title = (m.group(1).strip() if m else "")
        body  = extracted.strip()
        text_final = prosody(title, body)
    else:
        text_final = prosody("", text or "")

    # Demo cap for full reads
    if DEMO_MODE:
        text_final = text_final[:MAX_CHARS]
    return await stream_tts_for_text(text_final, voice_id=VOICE_ID, model_id=MODEL_ID)


def _split_text_for_tts(t: str, target: int = 2200) -> list[str]:
    # Greedy paragraph-based splitting with sentence hints
    parts: list[str] = []
    buf: list[str] = []
    cur = 0
    for para in re.split(r"\n{2,}", t.strip()):
        p = para.strip()
        if not p:
            continue
        if cur + len(p) + 2 > target and buf:
            parts.append("\n\n".join(buf))
            buf = []
            cur = 0
        buf.append(p)
        cur += len(p) + 2
    if buf:
        parts.append("\n\n".join(buf))
    # If still too large chunks, hard split
    out: list[str] = []
    for chunk in parts:
        if len(chunk) <= target:
            out.append(chunk)
        else:
            for i in range(0, len(chunk), target):
                out.append(chunk[i:i+target])
    return out

