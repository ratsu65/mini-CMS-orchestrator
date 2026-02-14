from __future__ import annotations

import hashlib
import uuid


def make_news_id() -> str:
    return str(uuid.uuid4())


def dedupe_hash(source_url: str, title: str) -> str:
    payload = f"{source_url}|{title}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
