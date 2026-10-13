import datetime
from zoneinfo import ZoneInfo


def today_in_tz(tz_name: str) -> datetime.date:
    return datetime.datetime.now(ZoneInfo(tz_name)).date()
