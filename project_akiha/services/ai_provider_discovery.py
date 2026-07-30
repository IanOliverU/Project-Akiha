"""Privacy-safe AI provider connection checks and model discovery."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

JSONPayload = dict[str, Any]
Headers = Mapping[str, str]
DiscoveryTransport = Callable[[str, Headers, float], JSONPayload]


class AIProviderDiscoveryError(RuntimeError):
    """Raised when an AI provider cannot return a usable model catalog."""


@dataclass(frozen=True, slots=True)
class AIProviderDiscoveryRequest:
    """Connection details required to query one selected provider."""

    provider: str
    base_url: str
    api_key: str = ""
    timeout_seconds: float = 10.0


@dataclass(frozen=True, slots=True)
class AIProviderDiscoveryResult:
    """Available models returned by the selected provider."""

    provider: str
    models: tuple[str, ...]


def discover_ai_provider_models(
    request: AIProviderDiscoveryRequest,
    *,
    transport: DiscoveryTransport | None = None,
) -> AIProviderDiscoveryResult:
    """Check the selected endpoint and return its advertised model IDs."""
    base_url = request.base_url.rstrip("/")
    if request.provider == "ollama":
        url = f"{base_url}/api/tags"
        headers: dict[str, str] = {"Accept": "application/json"}
    else:
        url = f"{base_url}/models"
        headers = {"Accept": "application/json"}
        if request.api_key:
            headers["Authorization"] = f"Bearer {request.api_key}"

    payload = (transport or _get_json)(
        url,
        headers,
        min(max(request.timeout_seconds, 1.0), 15.0),
    )
    models = (
        _parse_ollama_models(payload)
        if request.provider == "ollama"
        else _parse_compatible_models(payload)
    )
    if not models:
        raise AIProviderDiscoveryError(
            f"{_provider_label(request.provider)} connected but returned no models."
        )
    return AIProviderDiscoveryResult(
        provider=request.provider,
        models=tuple(sorted(set(models), key=str.casefold)),
    )


def _get_json(url: str, headers: Headers, timeout_seconds: float) -> JSONPayload:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code in {401, 403}:
            detail = "The API key was rejected."
        elif error.code == 404:
            detail = "The model-catalog endpoint was not found."
        elif error.code == 429:
            detail = "The provider rate limit or quota was reached."
        else:
            detail = f"The provider returned HTTP {error.code}."
        raise AIProviderDiscoveryError(detail) from error
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AIProviderDiscoveryError(
            "Connection failed. Check the provider, endpoint, and network."
        ) from error

    if not isinstance(payload, dict):
        raise AIProviderDiscoveryError(
            "The provider returned an invalid model catalog."
        )
    return payload


def _parse_compatible_models(payload: JSONPayload) -> list[str]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise AIProviderDiscoveryError(
            "The provider response did not include a compatible model list."
        )
    return [
        model_id.strip()
        for item in data
        if isinstance(item, dict)
        and isinstance((model_id := item.get("id")), str)
        and model_id.strip()
    ]


def _parse_ollama_models(payload: JSONPayload) -> list[str]:
    data = payload.get("models")
    if not isinstance(data, list):
        raise AIProviderDiscoveryError(
            "Ollama response did not include an installed model list."
        )
    models: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        model_name = item.get("name", item.get("model"))
        if isinstance(model_name, str) and model_name.strip():
            models.append(model_name.strip())
    return models


def _provider_label(provider: str) -> str:
    return {
        "gemini": "Gemini",
        "grok": "Grok",
        "kimi": "Kimi",
        "ollama": "Ollama",
        "openai": "OpenAI",
        "openrouter": "OpenRouter",
    }.get(provider.casefold(), "AI provider")
