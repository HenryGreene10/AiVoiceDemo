import re
from typing import Tuple, Dict, Optional


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


CAPTION_PREFIXES = (
    "Photo:", "Photograph:", "Image:", "Illustration:", "Credit:",
    "Advertisement", "Ads by", "Subscribe", "Read more", "Recommended"
)

def strip_junk(text: str) -> str:
    if not text: return ""
    # Remove bracketed citations [1], [2]
    text = re.sub(r"\[\d+\]", "", text)
    # Remove “(IPA …)” / “(pronunciation …)” / “(/…/)”
    text = re.sub(r"\s*\((?:IPA|pronunciation|listen|/)[^)]+\)\s*", " ", text, flags=re.I)
    # Remove raw URLs
    text = re.sub(r"https?://\S+", "", text)
    # Remove “[citation needed]” etc.
    text = re.sub(r"\[(?:citation|clarification|verification)\s+needed\]", "", text, flags=re.I)
    # Drop obvious caption/utility lines
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith(CAPTION_PREFIXES)]
    text = " ".join(lines)
    # Normalize spacing/punctuation
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?=\S)", r"\1 ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text

def build_narration(title: str, author: Optional[str], body: str) -> str:
    # Clear, audible intro → short pause → story
    header = f"{title.strip().rstrip('.')} . "
    if author and author.strip():
        header += f"By {author.strip().rstrip('.')} . "
    # Light “prosody scaffolding”: break long sentences; add clause pauses
    body = re.sub(r"[,;] ", ", ", body)               # keep commas natural
    body = re.sub(r"\b—\b", ", ", body)               # em-dash → pause
    body = re.sub(r"\s*\(\s*[^)]+\)\s*", " ", body)   # parenthetical aside
    return f"{header}\n{body}".strip()

def prepare_article(title: str, author: Optional[str], text: str) -> str:
    return build_narration(strip_junk(title or "Untitled"),
                           author or "",
                           strip_junk(text or ""))


def prosody_settings_for(title: str, body: str) -> Dict:
    style = 0.40
    stability = 0.38
    similarity = 0.88
    if "?" in (title or "") or "!" in (title or ""):
        style += 0.05
    if len(body or "") < 600:
        stability += 0.05
    return {
        "stability": round(stability, 2),
        "similarity_boost": round(similarity, 2),
        "style": round(style, 2),
        "use_speaker_boost": True,
    }

