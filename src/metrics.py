import os
import csv
import io
import time
import boto3


_s3 = boto3.client("s3", region_name=os.getenv("REGION", os.getenv("AWS_REGION", "us-east-1")))


def _bucket() -> str:
    b = os.getenv("S3_BUCKET", "").strip()
    if not b:
        raise RuntimeError("S3_BUCKET not set")
    return b


def append_stream_row(ts_ms: int, source: str, first_audio_ms: int, total_bytes: int, model_id: str, cache_key: str) -> None:
    key = "metrics/streams.csv"
    # MVP approach: get, append, put back (race conditions acceptable for MVP)
    try:
        try:
            obj = _s3.get_object(Bucket=_bucket(), Key=key)
            body = obj["Body"].read()
        except _s3.exceptions.NoSuchKey:  # type: ignore[attr-defined]
            body = b""
        except Exception:
            body = b""

        output = io.StringIO()
        if not body:
            # write header
            output.write("ts_ms,source,first_audio_ms,total_bytes,model_id,cache_key\n")
        else:
            output.write(body.decode("utf-8", errors="ignore"))
        w = csv.writer(output)
        w.writerow([ts_ms, source, first_audio_ms, total_bytes, model_id, cache_key])
        data = output.getvalue().encode("utf-8")
        _s3.put_object(Bucket=_bucket(), Key=key, Body=data, ContentType="text/csv")
    except Exception:
        # best-effort, ignore
        pass


