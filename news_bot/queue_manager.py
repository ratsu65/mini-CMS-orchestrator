from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from news_bot.database import Database
from news_bot.models import QueueType

logger = logging.getLogger(__name__)


WorkerFn = Callable[[str], Awaitable[None]]


class QueueWorker:
    def __init__(self, db: Database, queue_type: QueueType, worker_fn: WorkerFn, delay_range: tuple[int, int] | None = None) -> None:
        self.db = db
        self.queue_type = queue_type
        self.worker_fn = worker_fn
        self.delay_range = delay_range
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
            row = await self.db.pop_queue(self.queue_type)
            if not row:
                await asyncio.sleep(1)
                continue
            news_id = row["news_id"]
            try:
                await self.worker_fn(news_id)
            except Exception:
                logger.exception("worker failed queue=%s news_id=%s", self.queue_type, news_id)
            if self.delay_range:
                await asyncio.sleep(random.randint(*self.delay_range))


class QueueManager:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._workers: list[QueueWorker] = []

    def setup_workers(self, scrape_fn: WorkerFn, upload_fn: WorkerFn, publish_fn: WorkerFn) -> None:
        self._workers = [
            QueueWorker(self.db, QueueType.SCRAPE, scrape_fn),
            QueueWorker(self.db, QueueType.UPLOAD, upload_fn),
            QueueWorker(self.db, QueueType.PUBLISH, publish_fn, delay_range=(120, 240)),
        ]

    def start(self) -> None:
        for worker in self._workers:
            worker.start()

    async def stop(self) -> None:
        await asyncio.gather(*(worker.stop() for worker in self._workers), return_exceptions=True)

    async def clear(self) -> None:
        await self.db.execute("DELETE FROM queues")
