from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo
import os


@dataclass(slots=True)
class CMSUser:
    username: str
    password: str


@dataclass(slots=True)
class Settings:
    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    db_path: Path = field(init=False)
    blacklist_path: Path = field(init=False)
    cookies_path: Path = field(init=False)
    rss_interval_seconds: int = 120
    scrape_retry_count: int = 3
    upload_retry_count: int = 3
    publish_retry_count: int = 3
    cms_login_url: str = "https://www.didbaniran.ir/admin-start-GeHid0Greph"
    cms_add_url: str = "https://www.didbaniran.ir/fa/admin/newsstudios/add/"
    tehran_tz: ZoneInfo = field(default_factory=lambda: ZoneInfo("Asia/Tehran"))
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    allowed_chat_id: int | None = field(default_factory=lambda: int(os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "0")) or None)
    rss_feeds: list[str] = field(default_factory=lambda: [
        "https://www.khabaronline.ir/rss",
    ])

    def __post_init__(self) -> None:
        self.db_path = self.base_dir / "news_automation.db"
        self.blacklist_path = self.base_dir / "blacklist.txt"
        self.cookies_path = self.base_dir / "cms_cookies.json"


SETTINGS = Settings()
