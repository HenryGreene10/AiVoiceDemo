import os
from typing import Optional, List
import boto3
from botocore.exceptions import ClientError


_s3 = boto3.client("s3", region_name=os.getenv("REGION", os.getenv("AWS_REGION", "us-east-1")))


def get_bucket_name() -> str:
    b = os.getenv("S3_BUCKET", "").strip()
    if not b:
        raise RuntimeError("S3_BUCKET not set")
    return b


async def exists(cache_key: str) -> bool:
    try:
        _s3.head_object(Bucket=get_bucket_name(), Key=f"cache/{cache_key}.mp3")
        return True
    except ClientError as e:
        if e.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404 or e.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
            return False
        return False


async def put_audio(cache_key: str, data: bytes) -> None:
    _s3.put_object(
        Bucket=get_bucket_name(),
        Key=f"cache/{cache_key}.mp3",
        Body=data,
        ContentType="audio/mpeg",
    )


async def get_audio_url(cache_key: str) -> str:
    return _s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": get_bucket_name(), "Key": f"cache/{cache_key}.mp3"},
        ExpiresIn=24 * 3600,
    )


async def current_cache_bytes() -> int:
    total = 0
    paginator = _s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=get_bucket_name(), Prefix="cache/"):
        for obj in page.get("Contents", []) or []:
            total += int(obj.get("Size", 0))
    return total


async def reap_lru_if_needed():
    cap = int(os.getenv("MAX_CACHE_BYTES", "2000000000"))
    total = await current_cache_bytes()
    if total <= cap:
        return
    # list all then sort by LastModified
    objs: List[dict] = []
    paginator = _s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=get_bucket_name(), Prefix="cache/"):
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


