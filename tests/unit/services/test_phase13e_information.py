"""Fixed read-only weather endpoints, uncertainty, privacy and local routing."""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from project_akiha.config import AppConfig, UtilitiesConfig
from project_akiha.core.actions import (
    ActionCancellationToken,
    ActionPermissionPolicy,
    ActionRequestValidator,
    ActionStatus,
    PermissionDecision,
    ProtectedPathPolicy,
    build_default_action_registry,
)
from project_akiha.services.assistant_action_bridge import AssistantActionRequestParser
from project_akiha.services.config_store import _serialize_config
from project_akiha.services.current_information import (
    MAX_INFORMATION_BYTES,
    OpenMeteoInformationProvider,
    WeatherActionExecutor,
    read_information_json,
)


def payload():
    return {
        "current": {
            "time": "2026-10-09T00:00",
            "temperature_2m": 21,
            "wind_speed_10m": 5,
            "weather_code": 0,
        },
        "daily": {
            "time": ["2026-10-09", "2026-10-10", "2026-10-11"],
            "temperature_2m_min": [20, 21, 22],
            "temperature_2m_max": [24, 25, 26],
        },
        "PRIVATE_RAW_SENTINEL": {"provider_payload": "Never render or store me"},
    }


class CurrentInformationTest(unittest.TestCase):
    def weather_action(self):
        return ActionRequestValidator(
            build_default_action_registry(), ProtectedPathPolicy(())
        ).validate(AssistantActionRequestParser().parse("Weather"))

    def test_rate_limit_is_bounded_unavailable_without_private_exception_text(self):
        config = UtilitiesConfig(True, True, 25, 121)
        provider = Mock()
        provider.fetch.side_effect = HTTPError(
            "https://api.open-meteo.com", 429, "PRIVATE_NETWORK_SENTINEL", None, None
        )
        result = asyncio.run(
            WeatherActionExecutor(
                lambda: config, "information.weather.current", provider
            ).execute(
                self.weather_action(), cancellation_token=ActionCancellationToken()
            )
        )
        self.assertIs(result.status, ActionStatus.UNAVAILABLE)
        self.assertIn("rate limited", result.summary)
        self.assertNotIn("PRIVATE_NETWORK_SENTINEL", repr(result))

    def test_location_revocation_during_fetch_discards_response(self):
        config = [UtilitiesConfig(True, True, 25, 121)]
        provider = Mock()

        def fetch(*args, **kwargs):
            config[0] = replace(config[0], weather_enabled=False)
            return self.provider(lambda _: payload()).fetch(25, 121)

        provider.fetch.side_effect = fetch
        result = asyncio.run(
            WeatherActionExecutor(
                lambda: config[0], "information.weather.current", provider
            ).execute(
                self.weather_action(), cancellation_token=ActionCancellationToken()
            )
        )
        self.assertIs(result.status, ActionStatus.CANCELLED)
        self.assertNotIn("weather_display", result.metadata)

    def test_cancel_before_fetch_makes_no_network_request(self):
        provider = Mock()
        token = ActionCancellationToken()
        token.cancel()
        result = asyncio.run(
            WeatherActionExecutor(
                lambda: UtilitiesConfig(True, True, 25, 121),
                "information.weather.current",
                provider,
            ).execute(self.weather_action(), cancellation_token=token)
        )
        self.assertIs(result.status, ActionStatus.CANCELLED)
        provider.fetch.assert_not_called()

    def provider(self, reader):
        return OpenMeteoInformationProvider(
            reader, now=lambda: datetime(2026, 10, 9, 0, 5, tzinfo=UTC)
        )

    def test_current_forecast_source_timestamp_units_and_uncertainty(self):
        reader = Mock(return_value=payload())
        snapshot = self.provider(reader).fetch(25, 121, official_alerts=False)
        text = snapshot.render(forecast=True)
        self.assertIn("Open-Meteo", text)
        self.assertIn("age 5 minutes", text)
        self.assertIn("actual local weather may differ", text)
        self.assertIn("°C", text)
        self.assertIn("2026-10-11", text)
        self.assertNotIn("PRIVATE_RAW_SENTINEL", text)
        self.assertEqual(reader.call_count, 1)
        self.assertTrue(
            reader.call_args.args[0].startswith(
                "https://api.open-meteo.com/v1/forecast?"
            )
        )

    def test_stale_conditions_are_labelled(self):
        data = payload()
        data["current"]["time"] = "2026-10-08T00:00"
        self.assertIn(
            "Stale conditions",
            self.provider(lambda _: data)
            .fetch(25, 121, official_alerts=False)
            .render(),
        )

    def test_offline_propagates_without_raw_payload(self):
        reader = Mock(side_effect=OSError("synthetic offline"))
        with self.assertRaises(OSError):
            self.provider(reader).fetch(25, 121, official_alerts=False)

    def test_malformed_unbounded_measurements_and_future_timestamp_reject(self):
        for field, value in [
            ("temperature_2m", float("nan")),
            ("temperature_2m", True),
            ("wind_speed_10m", -1),
            ("weather_code", 100),
            ("time", "2027-10-09T00:00"),
        ]:
            with self.subTest(field=field, value=value):
                data = payload()
                data["current"][field] = value
                with self.assertRaises(ValueError):
                    self.provider(lambda _, data=data: data).fetch(
                        25, 121, official_alerts=False
                    )

    def test_malformed_daily_shape_rejects(self):
        for replacement in [[], ["private"], ["2026-10-09"] * 4]:
            data = payload()
            data["daily"]["time"] = replacement
            with self.assertRaises(ValueError):
                self.provider(lambda _, data=data: data).fetch(
                    25, 121, official_alerts=False
                )

    def test_official_alerts_bounded_and_never_interpreted_as_actions(self):
        reader = Mock(
            side_effect=[
                payload(),
                {
                    "features": [
                        {"properties": {"headline": "Synthetic official alert"}}
                    ]
                    * 5
                },
            ]
        )
        snapshot = self.provider(reader).fetch(40, -75, official_alerts=True)
        self.assertEqual(len(snapshot.alerts), 3)
        self.assertIn("5 active", snapshot.alert_status)
        self.assertTrue(
            reader.call_args.args[0].startswith(
                "https://api.weather.gov/alerts/active?"
            )
        )

    def test_alert_error_and_outside_coverage_never_claim_all_clear(self):
        reader = Mock(side_effect=[payload(), OSError("offline")])
        snapshot = self.provider(reader).fetch(40, -75, official_alerts=True)
        self.assertIn("do not infer an all-clear", snapshot.alert_status)
        other = Mock(return_value=payload())
        snapshot = self.provider(other).fetch(25, 121, official_alerts=True)
        self.assertIn("unavailable for this location", snapshot.alert_status)
        self.assertEqual(other.call_count, 1)

    def test_unsafe_endpoints_rejected_before_network(self):
        with patch("project_akiha.services.current_information.build_opener") as opener:
            for url in [
                "http://api.open-meteo.com/v1/forecast",
                "https://127.0.0.1/v1/forecast",
                "https://api.open-meteo.com.evil/v1/forecast",
                "https://api.open-meteo.com/v1/delete",
                "https://api.weather.gov/actions/run",
                "file:///secret",
            ]:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    read_information_json(url)
            opener.assert_not_called()

    def test_response_size_bounded_and_redirects_disabled(self):
        response = Mock()
        response.status = 200
        response.read.return_value = b"x" * (MAX_INFORMATION_BYTES + 1)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch(
            "project_akiha.services.current_information.build_opener",
            return_value=opener,
        ):
            with self.assertRaises(ValueError):
                read_information_json("https://api.open-meteo.com/v1/forecast")
        response.read.assert_called_once_with(MAX_INFORMATION_BYTES + 1)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 6)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")

    def test_explicit_configuration_roundtrip_and_no_location_in_repr(self):
        import tomllib

        config = AppConfig(
            utilities=UtilitiesConfig(True, True, 25.12345, 121.54321, False, 30)
        )
        data = tomllib.loads(_serialize_config(config))
        self.assertEqual(data["utilities"]["latitude"], 25.12345)
        self.assertNotIn("25.12345", repr(config))
        self.assertFalse(AppConfig().utilities.location_configured)
        for latitude in [float("nan"), True, 91]:
            with self.assertRaises(ValueError):
                UtilitiesConfig(latitude=latitude)

    def test_specific_weather_commands_route_locally_arbitrary_urls_do_not(self):
        parser = AssistantActionRequestParser()
        self.assertEqual(
            parser.parse("Akiha, please show weather").action_id,
            "information.weather.current",
        )
        self.assertEqual(
            parser.parse("Weather forecast").action_id, "information.weather.forecast"
        )
        self.assertIsNone(parser.parse("Weather at https://example.com"))

    def test_weather_requires_explicit_local_request(self):
        registry = build_default_action_registry()
        paths = ProtectedPathPolicy(())
        request = AssistantActionRequestParser().parse("Weather")
        action = ActionRequestValidator(registry, paths).validate(request)
        self.assertIs(
            ActionPermissionPolicy(paths).evaluate(action, ()),
            PermissionDecision.GRANTED,
        )
        from dataclasses import replace

        forged = replace(request, source="provider.gemini")
        action = ActionRequestValidator(registry, paths).validate(forged)
        self.assertIs(
            ActionPermissionPolicy(paths).evaluate(action, ()),
            PermissionDecision.MISSING,
        )
