from __future__ import annotations

from pathlib import Path

import aiofiles
from bs4 import BeautifulSoup, Tag


class ContentCleaner:
    def __init__(self, blacklist_path: Path) -> None:
        self.blacklist_path = blacklist_path
        self.blacklist: set[str] = set()

    async def load_blacklist(self) -> None:
        if not self.blacklist_path.exists():
            self.blacklist_path.write_text("", encoding="utf-8")
        async with aiofiles.open(self.blacklist_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in await f.readlines()]
        self.blacklist = {line for line in lines if line}

    async def add_blacklist_phrase(self, phrase: str) -> None:
        phrase = phrase.strip()
        if not phrase:
            return
        if phrase in self.blacklist:
            return
        self.blacklist.add(phrase)
        async with aiofiles.open(self.blacklist_path, "a", encoding="utf-8") as f:
            await f.write(phrase + "\n")

    def clean(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        body = soup.select_one('div.item-text[itemprop="articleBody"]') or soup

        for block in body.select(".ads, .related, .related-content, .advertisement, .item-code"):
            block.decompose()

        for pre in body.find_all(["pre", "code"]):
            pre.decompose()

        for a_tag in body.find_all("a"):
            a_tag.replace_with(a_tag.get_text(strip=True))

        if self.blacklist:
            for text_node in body.find_all(string=True):
                content = str(text_node)
                updated = content
                for phrase in self.blacklist:
                    updated = updated.replace(phrase, "")
                if updated != content:
                    text_node.replace_with(updated)

        return self._compact_html(body)

    def _compact_html(self, root: Tag) -> str:
        html = str(root)
        return "\n".join(line for line in html.splitlines() if line.strip())
