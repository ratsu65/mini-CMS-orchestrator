from __future__ import annotations

import json
from pathlib import Path

from playwright.async_api import BrowserContext, Page, TimeoutError, async_playwright

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

    async def _fill_first(self, page: Page, selectors: list[str], value: str, timeout_ms: int = 15000) -> None:
        last_error: Exception | None = None
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=timeout_ms)
                await locator.fill(value)
                return
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Could not find input field for selectors={selectors}") from last_error

    async def _click_first(self, page: Page, selectors: list[str], timeout_ms: int = 15000) -> None:
        last_error: Exception | None = None
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=timeout_ms)
                await locator.click()
                return
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Could not find clickable element for selectors={selectors}") from last_error

    async def ensure_login(self, username: str, password: str) -> None:
        if not await self.state_manager.needs_login():
            return
        page = await self.get_page()
        try:
            await page.goto(self.settings.cms_login_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(1000)

            await self._fill_first(
                page,
                [
                    "input[name='username']",
                    "input#username",
                    "input[type='text']",
                ],
                username,
            )
            await self._fill_first(
                page,
                [
                    "input[name='password']",
                    "input#password",
                    "input[type='password']",
                ],
                password,
            )
            await self._click_first(
                page,
                [
                    "button:has-text('ارسال')",
                    "button:has-text('OTP')",
                    "button[type='submit']",
                    "input[type='submit']",
                ],
            )

            otp_future = self.state_manager.prepare_otp_waiter()
            otp = await otp_future
            digits = [ch for ch in otp if ch.isdigit()][:6]
            if len(digits) != 6:
                raise ValueError("OTP must be exactly 6 digits")

            for idx, digit in enumerate(digits, start=1):
                await self._fill_first(
                    page,
                    [
                        f"input[name='otp{idx}']",
                        f"input[id='otp{idx}']",
                        f"input[name='code{idx}']",
                    ],
                    digit,
                    timeout_ms=10000,
                )

            await self._click_first(
                page,
                [
                    "button:has-text('ورود')",
                    "button:has-text('Login')",
                    "button[type='submit']",
                    "input[type='submit']",
                ],
            )
            await page.wait_for_load_state("networkidle", timeout=60000)
            cookies = await self._context.cookies() if self._context else []
            Path(self.settings.cookies_path).write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
            await self.state_manager.set_last_login_today()
        except TimeoutError as exc:
            raise RuntimeError("CMS login timeout: login form elements not found or did not load in time") from exc
        finally:
            await page.close()
