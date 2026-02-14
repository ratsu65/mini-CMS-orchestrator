from __future__ import annotations

from news_bot.cms.session_manager import CMSSessionManager
from news_bot.utils.jalali_time import jalali_timestamp, now_tehran


class CMSPublisher:
    def __init__(self, session_manager: CMSSessionManager) -> None:
        self.session_manager = session_manager

    async def publish(self, edit_url: str) -> None:
        page = await self.session_manager.get_page()
        try:
            await page.goto(edit_url, wait_until="domcontentloaded")
            await page.check("input[name='breaking']")
            await page.check("input[name='headline']")
            await page.check("input[name='telegram']")
            await page.check("input[name='is_published']")
            await page.fill("input[name='publish_datetime']", jalali_timestamp(now_tehran()))
            await page.click("button:has-text('ذخیره')")
            await page.wait_for_load_state("networkidle")
        finally:
            await page.close()
