from __future__ import annotations

import asyncio
import logging
import sys
import types
from datetime import datetime
from pathlib import Path

if __name__ == "__main__" and __package__ in {None, ""}:
    package_root = Path(__file__).resolve().parent
    shim = types.ModuleType("news_bot")
    shim.__path__ = [str(package_root)]
    sys.modules.setdefault("news_bot", shim)

from news_bot.cleaner import ContentCleaner
from news_bot.cms.publisher import CMSPublisher
from news_bot.cms.session_manager import CMSSessionManager
from news_bot.cms.uploader import CMSUploader
from news_bot.config import SETTINGS
from news_bot.database import Database
from news_bot.models import NewsStatus, QueueType
from news_bot.queue_manager import QueueManager
from news_bot.rss_monitor import RSSMonitor
from news_bot.scheduler import Scheduler
from news_bot.scraper.khabaronline import KhabarOnlineScraper
from news_bot.state_manager import StateManager
from news_bot.telegram_bot import TelegramController

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.INFO)


PROFILE_PREFIX = {
    "didbaniran": '<p>به گزارش <a href="https://www.didbaniran.ir/"><strong>سایت دیده\u200cبان ایران</strong></a>،</p>',
}


class App:
    def __init__(self) -> None:
        self.settings = SETTINGS
        self.db = Database(self.settings.db_path)
        self.state_manager = StateManager(self.db)
        self.cleaner = ContentCleaner(self.settings.blacklist_path)
        self.rss_monitor = RSSMonitor(self.settings, self.db)
        self.scraper = KhabarOnlineScraper()
        self.session_manager = CMSSessionManager(self.settings, self.state_manager)
        self.uploader = CMSUploader(self.settings, self.session_manager)
        self.publisher = CMSPublisher(self.session_manager)
        self.queue_manager = QueueManager(self.db)
        self.telegram = TelegramController(
            self.settings,
            self.db,
            self.state_manager,
            self.queue_manager,
            self.cleaner,
        )
        self.scheduler = Scheduler(self.rss_monitor, self.queue_manager)

    async def initialize(self) -> None:
        await self.db.initialize()
        await self.cleaner.load_blacklist()
        await self.session_manager.start()
        self.queue_manager.setup_workers(self._scrape_worker, self._upload_worker, self._publish_worker)

    async def shutdown(self) -> None:
        await self.scheduler.stop()
        await self.telegram.stop()
        await self.session_manager.stop()

    async def _scrape_worker(self, news_id: str) -> None:
        row = await self.db.fetchone("SELECT * FROM news WHERE id = ?", (news_id,))
        if not row:
            return
        source_url = row["source_url"]
        for _ in range(self.settings.scrape_retry_count):
            try:
                scraped = await self.scraper.scrape(source_url)
                cleaned = self.cleaner.clean(scraped["content_html"] or "")
                state = await self.state_manager.get_state()
                profile = str(state.get("selected_profile") or "didbaniran")
                prefix = PROFILE_PREFIX.get(profile, "")
                content_html = f"{prefix}{cleaned}"
                now = datetime.utcnow().isoformat()
                await self.db.execute(
                    """
                    UPDATE news
                    SET title = ?, lead = ?, content_html = ?, image_path = ?, status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        scraped["title"] or row["title"],
                        scraped["lead"] or "",
                        content_html,
                        scraped["image_path"],
                        NewsStatus.SCRAPED.value,
                        now,
                        news_id,
                    ),
                )
                await self.db.add_queue(news_id, QueueType.UPLOAD)
                return
            except Exception:
                logger.exception("scrape retry failed news_id=%s", news_id)
                await asyncio.sleep(1)
        await self.db.execute("UPDATE news SET status = ? WHERE id = ?", (NewsStatus.FAILED.value, news_id))

    async def _upload_worker(self, news_id: str) -> None:
        state = await self.state_manager.get_state()
        username = state.get("selected_user")
        if not username:
            return
        creds = await self.db.fetchone("SELECT username, password FROM cms_users WHERE username = ?", (username,))
        if not creds:
            return
        row = await self.db.fetchone("SELECT * FROM news WHERE id = ?", (news_id,))
        if not row or row["status"] == NewsStatus.DELETED.value:
            return
        await self.session_manager.ensure_login(creds["username"], creds["password"])
        payload = {
            "title": row["title"],
            "lead": row["lead"],
            "category": row["category"],
            "content_html": row["content_html"],
            "image_path": row["image_path"],
        }
        for _ in range(self.settings.upload_retry_count):
            try:
                edit_url = await self.uploader.upload_news(payload)
                now = datetime.utcnow().isoformat()
                await self.db.execute(
                    "UPDATE news SET cms_edit_url = ?, status = ?, updated_at = ? WHERE id = ?",
                    (edit_url, NewsStatus.UPLOADED.value, now, news_id),
                )
                await self.telegram.send_uploaded_notification(news_id, row["title"], edit_url)
                return
            except Exception:
                logger.exception("upload retry failed news_id=%s", news_id)
                await asyncio.sleep(1)
        await self.db.execute("UPDATE news SET status = ? WHERE id = ?", (NewsStatus.FAILED.value, news_id))

    async def _publish_worker(self, news_id: str) -> None:
        row = await self.db.fetchone("SELECT cms_edit_url FROM news WHERE id = ?", (news_id,))
        if not row or not row["cms_edit_url"]:
            return
        for _ in range(self.settings.publish_retry_count):
            try:
                await self.publisher.publish(row["cms_edit_url"])
                await self.db.execute("UPDATE news SET status = ?, updated_at = ? WHERE id = ?", (NewsStatus.PUBLISHED.value, datetime.utcnow().isoformat(), news_id))
                return
            except Exception:
                logger.exception("publish retry failed news_id=%s", news_id)
                await asyncio.sleep(1)
        await self.db.execute("UPDATE news SET status = ? WHERE id = ?", (NewsStatus.FAILED.value, news_id))

    async def run(self) -> None:
        await self.initialize()
        await self.telegram.start()
        scheduler_running = False
        logger.info("system started")
        try:
            while True:
                state = await self.state_manager.get_state()
                bot_status = state.get("bot_status")
                if bot_status == "ON" and not scheduler_running:
                    self.scheduler.start()
                    scheduler_running = True
                    logger.info("automation workers started")
                elif bot_status != "ON" and scheduler_running:
                    await self.scheduler.stop()
                    scheduler_running = False
                    logger.info("automation workers stopped")
                await asyncio.sleep(1)
        finally:
            if scheduler_running:
                await self.scheduler.stop()
            await self.telegram.stop()
            await self.session_manager.stop()


async def main() -> None:
    app = App()
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
