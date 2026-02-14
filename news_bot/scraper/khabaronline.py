from __future__ import annotations

from playwright.async_api import async_playwright

from news_bot.scraper.base_scraper import BaseScraper


class KhabarOnlineScraper(BaseScraper):
    def __init__(self, headless: bool = True) -> None:
        self.headless = headless

    async def scrape(self, url: str) -> dict[str, str | None]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            html = await page.content()
            title = await page.title()
            lead = await page.locator("meta[name='description']").get_attribute("content")
            image = await page.locator("article img").first.get_attribute("src") if await page.locator("article img").count() else None
            await browser.close()
            return {
                "title": title.strip(),
                "lead": (lead or "").strip(),
                "content_html": html,
                "image_path": image,
            }
