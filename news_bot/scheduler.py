from __future__ import annotations

import asyncio

from news_bot.queue_manager import QueueManager
from news_bot.rss_monitor import RSSMonitor


class Scheduler:
    def __init__(self, rss_monitor: RSSMonitor, queue_manager: QueueManager) -> None:
        self.rss_monitor = rss_monitor
        self.queue_manager = queue_manager

    def start(self) -> None:
        self.rss_monitor.start()
        self.queue_manager.start()

    async def stop(self) -> None:
        await asyncio.gather(self.rss_monitor.stop(), self.queue_manager.stop())
