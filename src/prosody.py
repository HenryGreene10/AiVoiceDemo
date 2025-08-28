import re
from typing import Optional

CAPTION_PREFIXES = ("Photo:", "Photograph:", "Image:", "Illustration:", "Credit:",
                    "Advertisement", "Ads by", "Subscribe", "Read more", "Recommended")

def strip_junk(text: str) -> str:
    if not text: return ""
    text = re.sub(r"\[\d+\]", "", text)                                   # [1]
    text = re.sub(r"\s*\((?:IPA|pronunciation|listen|/)[^)]+\)\s*", " ", text, flags=re.I)
    text = re.sub(r"https?://\S+", "", text)                               # URLs
    text = re.sub(r"\[(?:citation|clarification|verification)\s+needed\]", "", text, flags=re.I)
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith(CAPTION_PREFIXES)]
    text = " ".join(lines)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?=\S)", r"\1 ", text)
    return re.sub(r"\s{2,}", " ", text).strip()

def build_narration(title: str, author: Optional[str], body: str) -> str:
    header = f"{title.strip().rstrip('.')}. "
    if author and author.strip(): header += f"By {author.strip().rstrip('.')}. "
    body = re.sub(r"\b—\b", ", ", body)                   # em-dash → pause
    body = re.sub(r"\s*\(\s*[^)]+\)\s*", " ", body)       # drop parentheticals
    return f"{header}\n{body}".strip()

def prepare_article(title: str, author: Optional[str], text: str) -> str:
    return build_narration(strip_junk(title or "Untitled"), author or "", strip_junk(text or ""))


