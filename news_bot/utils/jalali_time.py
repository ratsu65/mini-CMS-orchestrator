from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import jdatetime


TEHRAN = ZoneInfo("Asia/Tehran")


def now_tehran() -> datetime:
    return datetime.now(tz=TEHRAN)


def jalali_timestamp(dt: datetime | None = None) -> str:
    target = dt.astimezone(TEHRAN) if dt else now_tehran()
    jdt = jdatetime.datetime.fromgregorian(datetime=target.replace(tzinfo=None))
    return jdt.strftime("%Y/%m/%d %H:%M:%S")
