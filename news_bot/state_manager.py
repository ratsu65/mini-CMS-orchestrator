from __future__ import annotations

import asyncio
from datetime import date

from news_bot.database import Database


class StateManager:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._otp_waiter: asyncio.Future[str] | None = None

    async def get_state(self) -> dict[str, str | None]:
        row = await self.db.fetchone("SELECT bot_status, selected_profile, selected_user, last_login_date FROM state WHERE id = 1")
        if not row:
            return {
                "bot_status": "OFF",
                "selected_profile": "didbaniran",
                "selected_user": None,
                "last_login_date": None,
            }
        return dict(row)

    async def set_bot_status(self, status: str) -> None:
        await self.db.execute("UPDATE state SET bot_status = ? WHERE id = 1", (status,))

    async def set_profile(self, profile: str) -> None:
        await self.db.execute("UPDATE state SET selected_profile = ? WHERE id = 1", (profile,))

    async def set_selected_user(self, username: str | None) -> None:
        await self.db.execute("UPDATE state SET selected_user = ? WHERE id = 1", (username,))

    async def set_last_login_today(self) -> None:
        await self.db.execute("UPDATE state SET last_login_date = ? WHERE id = 1", (date.today().isoformat(),))

    async def needs_login(self) -> bool:
        state = await self.get_state()
        return state.get("last_login_date") != date.today().isoformat()

    def prepare_otp_waiter(self) -> asyncio.Future[str]:
        loop = asyncio.get_running_loop()
        self._otp_waiter = loop.create_future()
        return self._otp_waiter

    def submit_otp(self, otp: str) -> bool:
        if self._otp_waiter and not self._otp_waiter.done():
            self._otp_waiter.set_result(otp)
            return True
        return False
