from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class QueueType(StrEnum):
    SCRAPE = "SCRAPE"
    UPLOAD = "UPLOAD"
    PUBLISH = "PUBLISH"


class NewsStatus(StrEnum):
    NEW = "NEW"
    SCRAPED = "SCRAPED"
    UPLOADED = "UPLOADED"
    PUBLISHED = "PUBLISHED"
    DELETED = "DELETED"
    FAILED = "FAILED"


@dataclass(slots=True)
class NewsItem:
    id: str
    source_url: str
    title: str
    lead: str
    content_html: str
    image_path: str | None
    category: str
    status: str
    cms_edit_url: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class QueueItem:
    id: int
    news_id: str
    queue_type: QueueType
    priority: int
    created_at: datetime
