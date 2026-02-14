from __future__ import annotations

from abc import ABC, abstractmethod


class BaseScraper(ABC):
    @abstractmethod
    async def scrape(self, url: str) -> dict[str, str | None]:
        raise NotImplementedError
