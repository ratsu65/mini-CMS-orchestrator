from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import feedparser

from news_bot.config import Settings
from news_bot.database import Database
from news_bot.models import NewsStatus, QueueType
from news_bot.utils.id_generator import dedupe_hash, make_news_id

logger = logging.getLogger(__name__)


class RSSMonitor:
    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.check_once()
            except Exception:
                logger.exception("rss monitor failed")
            await asyncio.sleep(self.settings.rss_interval_seconds)

    async def check_once(self) -> None:
        for feed_url in self.settings.rss_feeds:
            feed = await asyncio.to_thread(feedparser.parse, feed_url)
            for entry in feed.entries:
                source_url = entry.get("link", "").strip()
                title = entry.get("title", "").strip()
                if not source_url or not title:
                    continue
                digest = dedupe_hash(source_url, title)
                exists = await self.db.fetchone("SELECT hash FROM seen_hashes WHERE hash = ?", (digest,))
                if exists:
                    continue
                news_id = make_news_id()
                now = datetime.utcnow().isoformat()
                await self.db.execute(
                    """
                    INSERT INTO news(id, source_url, title, lead, content_html, image_path, category, status, cms_edit_url, created_at, updated_at)
                    VALUES (?, ?, ?, '', '', NULL, 'سیاسی', ?, NULL, ?, ?)
                    """,
                    (news_id, source_url, title, NewsStatus.NEW.value, now, now),
                )
                await self.db.execute("INSERT INTO seen_hashes(hash, created_at) VALUES (?, ?)", (digest, now))
                await self.db.add_queue(news_id, QueueType.SCRAPE)
