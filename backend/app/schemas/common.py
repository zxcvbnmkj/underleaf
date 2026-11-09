from datetime import UTC, datetime
from typing import Annotated

from pydantic import PlainSerializer


def _to_utc_iso(value: datetime) -> str:
    # 数据库中存的是 UTC 但不带时区；补上时区并以 Z 结尾，否则浏览器会按本地时间解析
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


UtcDatetime = Annotated[datetime, PlainSerializer(_to_utc_iso, return_type=str)]
