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
