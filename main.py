# main.py
import os, hashlib, requests, time, httpx
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

# --- TTS request (streaming)
@app.post("/tts")
async def tts(req: TTSRequest):
    # allow hardcoded sample text to test end-to-end streaming
    sample_text = (
        "This is a short sample paragraph to verify streaming text to speech. "
        "Audio should begin quickly and continue without interruption."
    )
    text = (req.text or "").strip() or sample_text
    voice_id = VOICE_ID

    # if cached, return immediately (non-streaming fast path)
    k = cache_key(text, voice_id)
    if k in cache:
        return Response(content=cache[k], media_type="audio/mpeg")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {
        "xi-api-key": API_KEY,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2",
        "voice_settings": {
            "stability": 0.35,
            "similarity_boost": 0.9,
            "style": 0.35,
            "use_speaker_boost": True,
        },
        "optimize_streaming_latency": 2,
    }

    client: httpx.AsyncClient = app.state.http_client

    start_time = time.time()
    buffer = bytearray()
    first_chunk_time: float | None = None
    total_bytes = 0

    async def stream_tts():
        nonlocal first_chunk_time, total_bytes
        try:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    raise HTTPException(status_code=resp.status_code, detail=err[:200].decode(errors="ignore"))
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    if not chunk:
                        continue
                    if first_chunk_time is None:
                        first_chunk_time = time.time()
                    total_bytes += len(chunk)
                    buffer.extend(chunk)
                    yield chunk
        finally:
            # log basic metrics
            start_ms = int((start_time) * 1000)
            first_audio_ms = int(((first_chunk_time or time.time()) - start_time) * 1000)
            print({
                "event": "tts_stream",
                "start_ms": start_ms,
                "first_audio_ms": first_audio_ms,
                "total_bytes": total_bytes,
            })
            # cache the full audio if any was produced
            if total_bytes > 0:
                try:
                    cache.put(k, bytes(buffer))
                except Exception:
                    pass

    return StreamingResponse(stream_tts(), media_type="audio/mpeg")

# --- TTS GET for direct <audio src>
@app.get("/tts")
async def tts_get(text: str = Query("", min_length=0)):
    return await tts(TTSRequest(text=text))

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
@app.post("/read")
def read(req: ReadRequest):
    if not (req.text or req.url):
        raise HTTPException(400, "Provide 'text' or 'url'")
    if req.url:
        if not is_public_http_url(req.url):
            raise HTTPException(400, "Invalid URL")
        r = http.get(req.url, timeout=8, headers={"User-Agent":"Mozilla/5.0 (ReaderBot)"})
        if r.status_code != 200 or not r.text:
            raise HTTPException(502, "Fetch failed")
        extracted = trafilatura.extract(r.text, include_comments=False, include_tables=False,
                                favor_precision=True)
        if not extracted:
            raise HTTPException(422, "No article content found")

        m = re.search(r"<title[^>]*>(.*?)</title>", r.text, flags=re.I|re.S)
        title = (m.group(1).strip() if m else "")
        body  = extracted.strip()

        text  = prosody(title, body)
    else:
        text = prosody("", req.text)

    # reuse your TTS flow
    voice_id = VOICE_ID
    k = cache_key(text, voice_id)
    if k in cache:
        return Response(content=cache[k], media_type="audio/mpeg")

    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
        headers={"xi-api-key": API_KEY, "Content-Type": "application/json"},
        json={"text": text},
        timeout=60,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:200])

    cache.put(k, r.content)
    return Response(content=r.content, media_type="audio/mpeg")

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

# --- Read (GET) streaming with chunking for <audio src>
@app.get("/read")
async def read_get(url: str | None = None, text: str | None = None):
    if not (text or url):
        raise HTTPException(400, "Provide 'text' or 'url'")
    if url:
        if not is_public_http_url(url):
            raise HTTPException(400, "Invalid URL")
        r = http.get(url, timeout=8, headers={"User-Agent":"Mozilla/5.0 (ReaderBot)"})
        if r.status_code != 200 or not r.text:
            raise HTTPException(502, "Fetch failed")
        extracted = trafilatura.extract(r.text, include_comments=False, include_tables=False,
                                favor_precision=True)
        if not extracted:
            raise HTTPException(422, "No article content found")

        m = re.search(r"<title[^>]*>(.*?)</title>", r.text, flags=re.I|re.S)
        title = (m.group(1).strip() if m else "")
        body  = extracted.strip()

        text  = prosody(title, body)
    else:
        text = prosody("", text or "")

    chunks = _split_text_for_tts(text)
    client: httpx.AsyncClient = app.state.http_client
    url_api = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream"
    headers = {
        "xi-api-key": API_KEY,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }

    voice_payload_common = {
        "model_id": "eleven_turbo_v2",
        "voice_settings": {
            "stability": 0.35,
            "similarity_boost": 0.9,
            "style": 0.35,
            "use_speaker_boost": True,
        },
        "optimize_streaming_latency": 2,
    }

    async def stream_all():
        total_bytes = 0
        try:
            for idx, piece in enumerate(chunks):
                payload = dict(voice_payload_common)
                payload["text"] = piece
                async with client.stream("POST", url_api, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        err = await resp.aread()
                        raise HTTPException(status_code=resp.status_code, detail=err[:200].decode(errors="ignore"))
                    async for chunk in resp.aiter_bytes(chunk_size=4096):
                        if not chunk:
                            continue
                        total_bytes += len(chunk)
                        yield chunk
        finally:
            print({"event":"read_stream","chunks":len(chunks),"total_bytes":total_bytes})

    return StreamingResponse(stream_all(), media_type="audio/mpeg")

