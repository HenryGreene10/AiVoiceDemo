# save as scripts/generate_mp3.py
import os, json, requests, sys

API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel (example)
MODEL_ID = "eleven_multilingual_v2"

text_path = sys.argv[1] if len(sys.argv) > 1 else "demo.txt"
with open(text_path, "r", encoding="utf-8") as f:
    text = f.read()

out_path = "/cygwin/home/henry/first100kproject/demo.mp3"
os.makedirs(os.path.dirname(out_path), exist_ok=True)

url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
headers = {"xi-api-key": API_KEY}
payload = {
    "text": text,
    "model_id": MODEL_ID,
    "voice_settings": {"stability": 0.4, "similarity_boost": 0.8}
}

r = requests.post(url, headers=headers, json=payload)
r.raise_for_status()
with open(out_path, "wb") as f:
    f.write(r.content)

print(f"Saved -> {out_path}")
