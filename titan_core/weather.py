from __future__ import annotations

from urllib.parse import quote
from urllib.request import urlopen


def fetch_weather_summary(location_label: str = "Charlotte") -> str:
    url = f"https://wttr.in/{quote(location_label)}?format=3"
    with urlopen(url, timeout=10) as response:  # nosec B310
        return response.read().decode("utf-8", errors="replace").strip()
