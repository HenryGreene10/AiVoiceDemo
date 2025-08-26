import os
import hmac
import time
import hashlib
import base64
from typing import Set


def allowed_origins_set() -> Set[str]:
    csv = os.getenv("ALLOWED_ORIGINS", "").strip()
    if not csv:
        return set()
    return {o.strip() for o in csv.split(",") if o.strip()}


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _consteq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def issue_token(origin: str, path: str, exp_ts: int) -> str:
    secret = os.getenv("TOKEN_SECRET", "").encode("utf-8")
    msg = f"{origin}|{path}|{exp_ts}".encode("utf-8")
    sig = hmac.new(secret, msg, hashlib.sha256).digest()
    return f"{exp_ts}.{_b64url(sig)}"


def verify_token(token: str, origin: str, path: str) -> bool:
    try:
        exp_str, sig_b64 = token.split(".", 1)
        exp = int(exp_str)
    except Exception:
        return False
    if exp < int(time.time()) - 5:  # small clock skew
        return False
    secret = os.getenv("TOKEN_SECRET", "").encode("utf-8")
    msg = f"{origin}|{path}|{exp}".encode("utf-8")
    good = _b64url(hmac.new(secret, msg, hashlib.sha256).digest())
    return _consteq(good, sig_b64)


