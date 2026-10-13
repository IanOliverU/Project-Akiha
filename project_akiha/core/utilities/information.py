"""Transient, provider-neutral weather information without execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

WEATHER_ACTIONS = ("information.weather.current", "information.weather.forecast")


@dataclass(frozen=True, slots=True)
class WeatherSnapshot:
    source: str
    measured_at: datetime
    fetched_at: datetime
    temperature_c: float
    wind_kmh: float
    weather_code: int
    forecast: tuple[tuple[str, float, float], ...]
    alerts: tuple[str, ...]
    alert_status: str

    def render(self, *, forecast: bool = False) -> str:
        age = max(0, (self.fetched_at - self.measured_at).total_seconds())
        lines = [
            f"Source: {self.source}; received {self.fetched_at.isoformat()}.",
            f"Conditions timestamp: {self.measured_at.isoformat()}; "
            f"age {int(age // 60)} minutes.",
            (
                "Stale conditions; verify at the source."
                if age > 3600
                else "Modelled conditions; actual local weather may differ."
            ),
            f"Temperature {self.temperature_c:g} °C; "
            f"wind {self.wind_kmh:g} km/h; WMO weather code {self.weather_code}.",
        ]
        if forecast:
            lines.append("Forecast estimates (daily minimum–maximum °C):")
            lines.extend(f"{day}: {low:g}–{high:g}" for day, low, high in self.forecast)
        lines.append(self.alert_status)
        lines.extend(self.alerts)
        return "\n".join(lines)


class CurrentInformationProvider(Protocol):
    def fetch(
        self, latitude: float, longitude: float, *, official_alerts: bool
    ) -> WeatherSnapshot: ...
