# main.py
import os, hashlib, requests
from collections import OrderedDict
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi import Query
import trafilatura, re, requests as http
from urllib.parse import urlparse
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
        return True
    except: return False

# --- TTS request
@app.post("/tts")
def tts(req: TTSRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(400, "Missing 'text'")
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
        # surface real error to help debugging
        raise HTTPException(status_code=r.status_code, detail=r.text[:200])

    cache.put(k, r.content)
    return Response(content=r.content, media_type="audio/mpeg")

# --- extract
@app.get("/extract")
def extract(url: str = Query(..., min_length=8)):
    if not is_public_http_url(url):
        raise HTTPException(400, "Invalid URL")
    try:
        r = http.get(url, timeout=8, headers={"User-Agent":"Mozilla/5.0 (ReaderBot)"})
        if r.status_code != 200 or not r.text:
            raise HTTPException(502, "Fetch failed")
        data = trafilatura.extract(r.text, include_comments=False, include_tables=False, favor_precision=True,  output="json")
        if not data: raise HTTPException(422, "No article content found")
        j = trafilatura.utils.json_to_dict(data)
        title = (j.get("title") or "").strip()
        text  = (j.get("text") or "").strip()
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
        data = trafilatura.extract(r.text, include_comments=False, include_tables=False,
                                   favor_precision=True, output="json")
        if not data:
            raise HTTPException(422, "No article content found")
        j = trafilatura.utils.json_to_dict(data)
        title = (j.get("title") or "").strip()
        body  = (j.get("text") or "").strip()
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

