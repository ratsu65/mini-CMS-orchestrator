from __future__ import annotations

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from news_bot.config import Settings
from news_bot.cms.session_manager import CMSSessionManager


class CMSUploader:
    def __init__(self, settings: Settings, session_manager: CMSSessionManager) -> None:
        self.settings = settings
        self.session_manager = session_manager

    async def upload_news(self, payload: dict[str, str | None]) -> str:
        page = await self.session_manager.get_page()
        try:
            await page.goto(self.settings.cms_add_url, wait_until="domcontentloaded")
            await page.fill("input[name='title']", payload.get("title") or "")
            await page.fill("textarea[name='lead']", payload.get("lead") or "")
            await page.select_option("select[name='category']", label=payload.get("category") or "سیاسی")
            await page.fill("input[name='tags']", "ایران")
            iframe = page.frame_locator("iframe")
            await iframe.locator("body").fill(payload.get("content_html") or "")
            await page.click("button:has-text('justify')")
            await page.select_option("select[name='position_front']", label="ویژه")
            await page.select_option("select[name='position_category']", label="سطح یک")
            if payload.get("image_path"):
                await page.set_input_files("input[type='file']", payload["image_path"])
            await page.click("button:has-text('ذخیره')")
            await page.wait_for_load_state("networkidle")
            return page.url
        except PlaywrightTimeoutError as exc:
            raise RuntimeError("CMS upload timeout") from exc
        finally:
            await page.close()
