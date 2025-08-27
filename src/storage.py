import os, pathlib, mimetypes
from typing import Optional, List
from botocore.exceptions import ClientError


USE_LOCAL = (os.getenv("S3_BUCKET", "").strip().lower() in ("", "local"))
LOCAL_DIR = pathlib.Path(os.getenv("LOCAL_CACHE_DIR", "./.cache")).resolve()

if not USE_LOCAL:
    import boto3
    _s3 = boto3.client("s3", region_name=os.getenv("REGION", os.getenv("AWS_REGION", "us-east-1")))


def get_bucket_name() -> str:
    if USE_LOCAL:
        return "local"
    b = os.getenv("S3_BUCKET", "").strip()
    if not b:
        raise RuntimeError("S3_BUCKET not set (or set S3_BUCKET=local to use LOCAL_CACHE_DIR)")
    return b


async def exists(cache_key: str) -> bool:
    if USE_LOCAL:
        return (LOCAL_DIR / cache_key).exists()
    try:
        _s3.head_object(Bucket=get_bucket_name(), Key=cache_key)
        return True
    except ClientError:
        return False


async def put_audio(cache_key: str, audio_bytes: bytes) -> None:
    if USE_LOCAL:
        path = (LOCAL_DIR / cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio_bytes)
    else:
        _s3.put_object(
            Bucket=get_bucket_name(),
            Key=cache_key,
            Body=audio_bytes,
            ContentType="audio/mpeg",
            CacheControl="public, max-age=31536000, immutable",
        )


async def get_audio_url(cache_key: str) -> str:
    if USE_LOCAL:
        # served by FastAPI static mount at /cache/
        return f"/cache/{cache_key}"
    else:
        # presigned S3 URL
        from boto3.session import Session
        session = Session()
        s3 = session.client("s3", region_name=os.getenv("REGION", os.getenv("AWS_REGION", "us-east-1")))
        return s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": get_bucket_name(), "Key": cache_key},
            ExpiresIn=3600,
        )


# helper for local static serving
def local_cache_path(cache_key: str):
    return (LOCAL_DIR / cache_key)


async def current_cache_bytes() -> int:
    if USE_LOCAL:
        if not LOCAL_DIR.exists():
            return 0
        total = 0
        for p in LOCAL_DIR.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
        return total
    # S3 fallback
    total = 0
    paginator = _s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=get_bucket_name()):
        for obj in page.get("Contents", []) or []:
            total += int(obj.get("Size", 0))
    return total


async def reap_lru_if_needed():
    cap = int(os.getenv("MAX_CACHE_BYTES", "2000000000"))
    total = await current_cache_bytes()
    if total <= cap:
        return
    if USE_LOCAL:
        files: list[pathlib.Path] = [p for p in LOCAL_DIR.rglob("*") if p.is_file()]
        # Oldest first by modification time
        files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0)
        for f in files:
            try:
                size = f.stat().st_size
            except OSError:
                size = 0
            try:
                f.unlink()
            except OSError:
                continue
            total -= size
            if total <= cap:
                break
        return
    # S3 fallback: list all then sort by LastModified
    objs: List[dict] = []
    paginator = _s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=get_bucket_name()):
        for obj in page.get("Contents", []) or []:
            objs.append(obj)
    objs.sort(key=lambda o: o.get("LastModified"))
    to_delete = []
    for o in objs:
        to_delete.append({"Key": o["Key"]})
        total -= int(o.get("Size", 0))
        if total <= cap:
            break
    if to_delete:
        # Batch delete up to 1000 at a time
        for i in range(0, len(to_delete), 1000):
            _s3.delete_objects(Bucket=get_bucket_name(), Delete={"Objects": to_delete[i:i+1000]})


