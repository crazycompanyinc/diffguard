"""GitHub webhook helpers."""

from __future__ import annotations

import hmac
import hashlib
import os


def verify_signature(body: bytes, signature: str | None, secret: str | None = None) -> bool:
    """Verify GitHub HMAC signature when a secret is configured."""

    secret = secret if secret is not None else os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        return True
    if not signature or not signature.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", signature)


def should_review_pull_request(payload: dict[str, object]) -> bool:
    return payload.get("action") in {"opened", "synchronize", "reopened", "ready_for_review"} and "pull_request" in payload
