"""Bounded fixed-host read-only weather and optional US official alerts."""

from __future__ import annotations

import asyncio
import json
import math
import re
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from project_akiha.core.actions import (
    ActionExecutionResult,
    ActionRequest,
    ActionStatus,
)
from project_akiha.core.utilities.information import WEATHER_ACTIONS, WeatherSnapshot

MAX_INFORMATION_BYTES = 524288


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_information_json(url: str) -> dict:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc not in {
        "api.open-meteo.com",
        "api.weather.gov",
    }:
        raise ValueError("Information endpoint is not allowlisted.")
    if (parsed.netloc == "api.open-meteo.com" and parsed.path != "/v1/forecast") or (
        parsed.netloc == "api.weather.gov" and parsed.path != "/alerts/active"
    ):
        raise ValueError("Information operation is not allowlisted.")
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Project-Akiha/0.1 (desktop weather)",
        },
        method="GET",
    )
    with build_opener(_NoRedirect()).open(request, timeout=6) as response:
        if response.status != 200:
            raise OSError("Information provider unavailable.")
        body = response.read(MAX_INFORMATION_BYTES + 1)
    if len(body) > MAX_INFORMATION_BYTES:
        raise ValueError("Information response exceeds its bound.")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("Information response is malformed.")
    return payload


def _number(value, low, high):
    if (
        type(value) not in (float, int)
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError("Information measurement is malformed.")
    return float(value)


class OpenMeteoInformationProvider:
    def __init__(self, reader=read_information_json, *, now=lambda: datetime.now(UTC)):
        self.reader = reader
        self.now = now

    def fetch(
        self, latitude: float, longitude: float, *, official_alerts: bool = False
    ) -> WeatherSnapshot:
        lat = _number(latitude, -90, 90)
        lon = _number(longitude, -180, 180)
        url = "https://api.open-meteo.com/v1/forecast?" + urlencode(
            {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,wind_speed_10m,weather_code",
                "daily": "temperature_2m_min,temperature_2m_max",
                "forecast_days": 3,
                "timezone": "UTC",
            }
        )
        data = self.reader(url)
        current = data["current"]
        if not isinstance(current["time"], str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", current["time"]
        ):
            raise ValueError("Conditions timestamp is malformed.")
        measured = datetime.fromisoformat(current["time"]).replace(tzinfo=UTC)
        if (measured - self.now()).total_seconds() > 600:
            raise ValueError("Conditions timestamp is unexpectedly in the future.")
        daily = data["daily"]
        dates = daily["time"]
        lows = daily["temperature_2m_min"]
        highs = daily["temperature_2m_max"]
        if (
            not isinstance(dates, list)
            or not 1 <= len(dates) <= 3
            or len(dates) != len(lows)
            or len(dates) != len(highs)
        ):
            raise ValueError("Forecast is malformed.")
        forecast = []
        for day, low, high in zip(dates, lows, highs, strict=True):
            if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                raise ValueError("Forecast timestamp is malformed.")
            datetime.fromisoformat(day)
            minimum = _number(low, -100, 70)
            maximum = _number(high, -100, 70)
            if minimum > maximum:
                raise ValueError("Forecast bounds are malformed.")
            forecast.append((day, minimum, maximum))
        alerts = ()
        alert_status = "Official alerts are not enabled; no all-clear is implied."
        if official_alerts:
            if -180 <= lon <= -60 and 15 <= lat <= 72:
                try:
                    payload = self.reader(
                        "https://api.weather.gov/alerts/active?"
                        + urlencode({"point": f"{lat},{lon}"})
                    )
                    features = payload["features"]
                    if not isinstance(features, list) or len(features) > 1000:
                        raise ValueError("Official alert response is malformed.")
                    labels = []
                    for feature in features[:3]:
                        headline = feature["properties"]["headline"]
                        if (
                            not isinstance(headline, str)
                            or not 1 <= len(headline) <= 320
                            or any(ord(c) < 32 for c in headline)
                        ):
                            raise ValueError("Official alert headline is malformed.")
                        labels.append(headline)
                    alerts = tuple(labels)
                    alert_status = (
                        f"Official NWS alerts: {len(features)} active; "
                        "showing up to 3. Source: api.weather.gov."
                    )
                except (OSError, ValueError, KeyError, TypeError):
                    alert_status = (
                        "Official NWS alerts unavailable; do not infer an all-clear."
                    )
            else:
                alert_status = (
                    "Official alerts are unavailable for this "
                    "location; check your local weather authority."
                )
        code = current["weather_code"]
        if type(code) is not int or not 0 <= code <= 99:
            raise ValueError("Weather code is malformed.")
        return WeatherSnapshot(
            "Open-Meteo (https://open-meteo.com)",
            measured,
            self.now(),
            _number(current["temperature_2m"], -100, 70),
            _number(current["wind_speed_10m"], 0, 500),
            code,
            tuple(forecast),
            alerts,
            alert_status,
        )


def parse_weather_command(text: str, correlation_id: str) -> ActionRequest | None:
    value = text.strip().casefold().rstrip(".!?")
    if value in {
        "weather",
        "show weather",
        "current weather",
        "what is the weather",
        "what's the weather",
    }:
        action = WEATHER_ACTIONS[0]
    elif value in {"weather forecast", "show weather forecast", "forecast"}:
        action = WEATHER_ACTIONS[1]
    else:
        return None
    return ActionRequest(correlation_id, action, "chat", {"service": "weather"})


class WeatherActionExecutor:
    def __init__(self, config_provider, action_id: str, provider=None):
        self.config_provider = config_provider
        self.provider = provider or OpenMeteoInformationProvider()
        self.action_id = action_id
        self.executor_id = action_id.replace(".", "_")

    async def execute(self, action, *, cancellation_token):
        config = self.config_provider()
        if cancellation_token.is_cancelled:
            return ActionExecutionResult(
                ActionStatus.CANCELLED, "Weather lookup cancelled."
            )
        if not config.weather_enabled or not config.location_configured:
            return ActionExecutionResult(
                ActionStatus.UNAVAILABLE,
                "Configure and enable weather in Settings → Utilities.",
            )
        captured = config
        try:
            snapshot = await asyncio.to_thread(
                self.provider.fetch,
                config.latitude,
                config.longitude,
                official_alerts=config.official_alerts,
            )
        except HTTPError as error:
            text = (
                "Weather provider rate limited; try later."
                if error.code == 429
                else "Weather provider unavailable; try later."
            )
            return ActionExecutionResult(ActionStatus.UNAVAILABLE, text)
        except (OSError, ValueError, KeyError, TypeError):
            return ActionExecutionResult(
                ActionStatus.UNAVAILABLE, "Weather unavailable or offline; try later."
            )
        if cancellation_token.is_cancelled or captured != self.config_provider():
            return ActionExecutionResult(
                ActionStatus.CANCELLED,
                "Weather lookup cancelled after settings changed.",
            )
        return ActionExecutionResult(
            ActionStatus.SUCCESS,
            "Weather is available in the local Utilities panel.",
            metadata={
                "weather_display": snapshot.render(
                    forecast=self.action_id == WEATHER_ACTIONS[1]
                )
            },
        )


def build_weather_executors(config_provider):
    return tuple(
        WeatherActionExecutor(config_provider, action_id)
        for action_id in WEATHER_ACTIONS
    )
