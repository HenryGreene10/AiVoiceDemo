import os, sys, json, argparse, requests, pathlib

def main():
    ap = argparse.ArgumentParser(description="One-shot TTS to MP3 (ElevenLabs)")
    ap.add_argument("-i", "--input",  default="demo-article.txt", help="Text file to read")
    ap.add_argument("-o", "--output", default="article-demo.mp3", help="Output MP3 path (e.g., ./article-demo.mp3 or public/audio/article-demo.mp3)")
    ap.add_argument("--voice", default="21m00Tcm4TlvDq8ikWAM", help="ElevenLabs voice id")
    ap.add_argument("--model", default="eleven_multilingual_v2", help="ElevenLabs model id")
    args = ap.parse_args()

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        sys.exit("ERROR: ELEVENLABS_API_KEY not set")

    # read text
    try:
        text = pathlib.Path(args.input).read_text(encoding="utf-8")
    except Exception as e:
        sys.exit(f"ERROR: cannot read input file {args.input}: {e}")

    # ensure output dir exists
    out_path = pathlib.Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{args.voice}"
    payload = {
        "text": text,
        "model_id": args.model,
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.8}
    }
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}

    print(f"[TTS] generating -> {out_path} ...")
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=180)
    if not r.ok:
        msg = r.text[:500]
        sys.exit(f"ERROR: TTS {r.status_code}: {msg}")

    out_path.write_bytes(r.content)
    print(f"[OK] saved: {out_path.resolve()}  ({len(r.content)//1024} KB)")

if __name__ == "__main__":
    main()
