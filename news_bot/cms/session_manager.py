from __future__ import annotations

import json
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

from news_bot.config import Settings
from news_bot.state_manager import StateManager


class CMSSessionManager:
    def __init__(self, settings: Settings, state_manager: StateManager) -> None:
        self.settings = settings
        self.state_manager = state_manager
        self._playwright = None
        self._browser = None
        self._context: BrowserContext | None = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context()
        if self.settings.cookies_path.exists():
            cookies = json.loads(self.settings.cookies_path.read_text(encoding="utf-8"))
            await self._context.add_cookies(cookies)

    async def stop(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def get_page(self) -> Page:
        if not self._context:
            raise RuntimeError("CMS session not started")
        return await self._context.new_page()

    async def ensure_login(self, username: str, password: str) -> None:
        if not await self.state_manager.needs_login():
            return
        page = await self.get_page()
        await page.goto(self.settings.cms_login_url, wait_until="domcontentloaded")
        await page.fill("input[name='username']", username)
        await page.fill("input[name='password']", password)
        await page.click("button:has-text('ارسال')")
        otp_future = self.state_manager.prepare_otp_waiter()
        otp = await otp_future
        digits = [ch for ch in otp if ch.isdigit()][:6]
        if len(digits) != 6:
            await page.close()
            raise ValueError("OTP must be exactly 6 digits")
        for idx, digit in enumerate(digits, start=1):
            await page.fill(f"input[name='otp{idx}']", digit)
        await page.click("button:has-text('ورود')")
        await page.wait_for_load_state("networkidle")
        cookies = await self._context.cookies() if self._context else []
        Path(self.settings.cookies_path).write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
        await self.state_manager.set_last_login_today()
        await page.close()
