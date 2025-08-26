import re
from typing import Tuple, Dict


NEG = {"dies","dead","death","shooting","war","massacre","earthquake","flood","famine","injured","tragedy","lawsuit","bankrupt","recall","layoffs","crash","toxic","drought","meltdown"}
POS = {"record","soared","booming","surge","breakthrough","discovery","wins","celebrates","milestone","landmark","thrilled","optimistic"}


def sentiment_from_title(title: str) -> str:
    t = (title or "").lower()
    n = sum(w in t for w in NEG)
    p = sum(w in t for w in POS)
    if n > p and n >= 2:
        return "sober"
    if p > n and p >= 2:
        return "upbeat"
    return "neutral"


def apply_ssml(text: str, tone: str) -> Tuple[str, Dict]:
    tone = (tone or "neutral").lower()
    # Insert breaks at paragraph boundaries
    clean = re.sub(r"\n{3,}", "\n\n", text.strip())
    parts = [p.strip() for p in re.split(r"\n{1,}", clean) if p.strip()]
    ssml_body = "".join(f"<p>{re.escape(p)}</p><break time=\"300ms\"/>" for p in parts)

    if tone == "sober":
        rate = "0.95"
        settings = {"stability": 0.25, "similarity_boost": 0.9, "style": 0.2, "use_speaker_boost": True}
    elif tone == "upbeat":
        rate = "1.05"
        settings = {"stability": 0.45, "similarity_boost": 0.9, "style": 0.5, "use_speaker_boost": True}
    else:
        rate = "1.0"
        settings = {"stability": 0.35, "similarity_boost": 0.9, "style": 0.35, "use_speaker_boost": True}

    ssml = f"<speak><prosody rate=\"{rate}\">{ssml_body}</prosody></speak>"
    return ssml, settings


def shape_text_for_tone(text: str, tone: str) -> Tuple[str, Dict]:
    return apply_ssml(text, tone)


