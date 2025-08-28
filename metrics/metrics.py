import csv, time
from pathlib import Path

METRICS_DIR = Path("metrics")
METRICS_DIR.mkdir(exist_ok=True)
METRICS_FILE = METRICS_DIR / "streams.csv"

def write_stream_row(event_time_ms: int, cache_status: str, ttfb_ms: int, total_bytes: int, model: str, h: str):
    is_new = not METRICS_FILE.exists()
    with METRICS_FILE.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["ts_ms","cache","ttfb_ms","bytes","model","hash"])
        w.writerow([event_time_ms, cache_status, ttfb_ms, total_bytes, model, h])


