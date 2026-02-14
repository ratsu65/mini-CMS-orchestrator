from __future__ import annotations

import asyncio
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from news_bot.models import QueueType


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    async def initialize(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS news (
                    id TEXT PRIMARY KEY,
                    source_url TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    lead TEXT NOT NULL DEFAULT '',
                    content_html TEXT NOT NULL DEFAULT '',
                    image_path TEXT,
                    category TEXT NOT NULL DEFAULT 'سیاسی',
                    status TEXT NOT NULL,
                    cms_edit_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    news_id TEXT NOT NULL,
                    queue_type TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 100,
                    created_at TEXT NOT NULL,
                    UNIQUE(news_id, queue_type)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    bot_status TEXT NOT NULL,
                    selected_profile TEXT NOT NULL,
                    selected_user TEXT,
                    last_login_date TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO state(id, bot_status, selected_profile, selected_user, last_login_date)
                VALUES (1, 'OFF', 'didbaniran', NULL, NULL)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cms_users (
                    username TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_hashes (
                    hash TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL
                )
                """
            )

    async def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        async with self._lock:
            await asyncio.to_thread(self._execute_sync, query, params)

    def _execute_sync(self, query: str, params: tuple[Any, ...]) -> None:
        with self._connect() as conn:
            conn.execute(query, params)

    async def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        async with self._lock:
            return await asyncio.to_thread(self._fetchone_sync, query, params)

    def _fetchone_sync(self, query: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
        with self._connect() as conn:
            cur = conn.execute(query, params)
            return cur.fetchone()

    async def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        async with self._lock:
            return await asyncio.to_thread(self._fetchall_sync, query, params)

    def _fetchall_sync(self, query: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
        with self._connect() as conn:
            cur = conn.execute(query, params)
            return list(cur.fetchall())

    async def add_queue(self, news_id: str, queue_type: QueueType, priority: int = 100) -> None:
        now = datetime.utcnow().isoformat()
        await self.execute(
            """
            INSERT OR IGNORE INTO queues(news_id, queue_type, priority, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (news_id, queue_type.value, priority, now),
        )

    async def pop_queue(self, queue_type: QueueType) -> sqlite3.Row | None:
        async with self._lock:
            return await asyncio.to_thread(self._pop_queue_sync, queue_type)

    def _pop_queue_sync(self, queue_type: QueueType) -> sqlite3.Row | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, news_id, queue_type, priority, created_at
                FROM queues
                WHERE queue_type = ?
                ORDER BY priority ASC, id ASC
                LIMIT 1
                """,
                (queue_type.value,),
            ).fetchone()
            if row:
                conn.execute("DELETE FROM queues WHERE id = ?", (row["id"],))
            return row
