# main.py
import os
from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()
assert os.getenv("ELEVENLABS_API_KEY"), "Set ELEVENLABS_API_KEY in .env"

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}

from fastapi import HTTPException
from fastapi.responses import Response
import requests

VOICE_ID = "REPLACE_WITH_VOICE_ID"  # ElevenLabs > Voices > copy ID

@app.post("/tts")
def tts(payload: dict):
    text = payload.get("text", "").strip()
    if not text:
        raise HTTPException(400, "Missing 'text'")

    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream",
        headers={
            "xi-api-key": os.getenv("ELEVENLABS_API_KEY"),
            "Content-Type": "application/json",
        },
        json={"text": text},
        timeout=60,
    )
    if r.status_code != 200:
        raise HTTPException(502, f"TTS failed: {r.text[:200]}")
    return Response(content=r.content, media_type="audio/mpeg")
