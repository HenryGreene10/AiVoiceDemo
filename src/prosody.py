import os, sys, json, argparse, requests, pathlib, re
from typing import Optional, Tuple

# -------------------------------
# Prosody helpers (yours, kept)
# -------------------------------
CAPTION_PREFIXES = ("Photo:", "Photograph:", "Image:", "Illustration:", "Credit:",
                    "Advertisement", "Ads by", "Subscribe", "Read more", "Recommended")

def strip_junk(text: str) -> str:
    if not text: return ""
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\s*\((?:IPA|pronunciation|listen|/)[^)]+\)\s*", " ", text, flags=re.I)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\[(?:citation|clarification|verification)\s+needed\]", "", text, flags=re.I)
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith(CAPTION_PREFIXES)]
    text = " ".join(lines)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?=\S)", r"\1 ", text)
    return re.sub(r"\s{2,}", " ", text).strip()

def build_narration(title: str, subtitle: str, author: Optional[str], body: str) -> str:
    parts = []
    if title:   parts.append(title.strip().rstrip(".") + ".")
    if subtitle:parts.append(subtitle.strip().rstrip(".") + ".")
    if author and author.strip():
        a = author.strip()
        # Normalize "By " if user passed bare name
        if not a.lower().startswith("by "): a = "By " + a
        parts.append(a.rstrip(".") + ".")
    # Light prosody nudges in body
    body = re.sub(r"\b—\b", ", ", body)            # em dash → pause
    body = re.sub(r"\s*\(\s*[^)]+\)\s*", " ", body) # drop parentheticals
    head = " ".join(parts)
    return f"{head}\n{body}".strip() if head else body.strip()

def prepare_article(title: str, subtitle: str, author: Optional[str], text: str) -> str:
    return build_narration(strip_junk(title or "Untitled"),
                           strip_junk(subtitle or ""),
                           author or "",
                           strip_junk(text or ""))

# -------------------------------
# Header parsing from file
# -------------------------------
def parse_header_from_file(raw: str) -> Tuple[str, str, str, str]:
    """
    Returns (title, subtitle, author, body) parsed from a file with this shape:
      Title
      Subtitle (optional)
      [blank]
      By Someone (optional, line begins with 'By ')
      [blank]
      Body...
    Any missing piece becomes "" and is *removed* from the body.
    """
    lines = raw.splitlines()
    # Trim leading blank lines
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1

    title, subtitle, author = "", "", ""
    # Title
    if i < len(lines) and lines[i].strip():
        title = lines[i].strip(); i += 1

    # Subtitle (next non-empty until a blank)
    if i < len(lines) and lines[i].strip():
        subtitle = lines[i].strip(); i += 1

    # Expect a blank separator (optional)
    if i < len(lines) and not lines[i].strip():
        i += 1

    # Author line beginning with "By "
    if i < len(lines) and lines[i].strip().lower().startswith("by "):
        author = lines[i].strip()[3:].strip()  # store bare name
        i += 1
        if i < len(lines) and not lines[i].strip():
            i += 1

    # Remainder is body
    body = "\n".join(lines[i:])
    return title, subtitle, author, body

# -------------------------------
# TTS script
# -------------------------------
def main():
    ap = argparse.ArgumentParser(description="One-shot TTS to MP3 (ElevenLabs) with title/subtitle parsing + prosody")
    ap.add_argument("-i", "--input",  default="demo-article.txt", help="Text file to read")
    ap.add_argument("-o", "--output", default="article-demo.mp3", help="Output MP3 path")
    ap.add_argument("--title", default=None, help="Override title")
    ap.add_argument("--subtitle", default=None, help="Override subtitle")
    ap.add_argument("--author", default=None, help="Override author (bare name, e.g., 'Henry Greene')")
    ap.add_argument("--voice", default="21m00Tcm4TlvDq8ikWAM", help="ElevenLabs voice id")
    ap.add_argument("--model", default="eleven_multilingual_v2", help="ElevenLabs model id")
    ap.add_argument("--stability", type=float, default=0.40)
    ap.add_argument("--similarity", type=float, default=0.80)
    ap.add_argument("--preview", action="store_true", help="Print first 300 chars of shaped text")
    args = ap.parse_args()

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        sys.exit("ERROR: ELEVENLABS_API_KEY not set")

    try:
        raw = pathlib.Path(args.input).read_text(encoding="utf-8")
    except Exception as e:
        sys.exit(f"ERROR: cannot read input file {args.input}: {e}")

    # Parse header from file, then apply CLI overrides if provided
    f_title, f_subtitle, f_author, f_body = parse_header_from_file(raw)
    title   = (args.title or f_title or "Untitled").strip()
    subtitle= (args.subtitle or f_subtitle or "").strip()
    author  = (args.author or f_author or "").strip()
    body    = f_body

    shaped = prepare_article(title, subtitle, author, body)

    if args.preview:
        print("\n[Prosody] Preview:\n", shaped[:300], "...\n")

    out_path = pathlib.Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{args.voice}"
    payload = {
        "text": shaped,
        "model_id": args.model,
        "voice_settings": {"stability": args.stability, "similarity_boost": args.similarity}
        # Optional: "output_format": "mp3_44100_128"
    }
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}

    print(f"[TTS] generating -> {out_path}  (chars={len(shaped)})")
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=180)
    if not r.ok:
        sys.exit(f"ERROR: TTS {r.status_code}: {r.text[:500]}")
    out_path.write_bytes(r.content)
    print(f"[OK] saved: {out_path.resolve()}  ({len(r.content)//1024} KB)")

if __name__ == "__main__":
    main()
