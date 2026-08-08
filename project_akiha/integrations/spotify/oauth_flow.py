"""Bounded loopback callback flow for Spotify desktop authorization."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from project_akiha.config import SpotifyConfig
from project_akiha.integrations.spotify.auth import (
    SpotifyOAuthError,
    SpotifyToken,
    create_spotify_authorization_session,
    exchange_spotify_authorization_code,
    parse_spotify_callback,
)


def authorize_spotify(
    config: SpotifyConfig,
    on_authorization_url: Callable[[str], None],
    cancel_event: threading.Event,
    *,
    wait_seconds: float = 180.0,
) -> SpotifyToken:
    """Open one bounded loopback listener and complete the PKCE exchange."""
    session = create_spotify_authorization_session(config)
    redirect = urlparse(config.redirect_uri)
    callback_target: list[str] = []
    callback_received = threading.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if urlparse(self.path).path != redirect.path:
                self.send_error(404)
                return
            callback_target.append(self.path)
            callback_received.set()
            body = (
                b"<!doctype html><meta charset=utf-8>"
                b"<title>Project Akiha</title>"
                b"<p>Spotify authorization received. You may close this tab.</p>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *args: object) -> None:
            del args

    try:
        server = HTTPServer(
            (redirect.hostname or "", redirect.port or 80),
            CallbackHandler,
        )
    except OSError as error:
        raise SpotifyOAuthError(
            "Spotify callback port 43821 is unavailable. Close the other app using it."
        ) from error

    server.timeout = 0.25
    try:
        on_authorization_url(session.authorization_url)
        deadline = time.monotonic() + wait_seconds
        while not callback_received.is_set():
            if cancel_event.is_set():
                raise SpotifyOAuthError("Spotify authorization was cancelled.")
            if time.monotonic() >= deadline:
                raise SpotifyOAuthError("Spotify authorization timed out.")
            server.handle_request()
    finally:
        server.server_close()

    if not callback_target:
        raise SpotifyOAuthError("Spotify authorization did not return a callback.")
    code = parse_spotify_callback(
        callback_target[0],
        expected_state=session.state,
        redirect_uri=session.redirect_uri,
    )
    return exchange_spotify_authorization_code(
        session,
        code,
        timeout_seconds=config.request_timeout_seconds,
    )
