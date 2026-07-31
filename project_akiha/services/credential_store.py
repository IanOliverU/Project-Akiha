"""Windows-user encrypted storage for API credentials and OAuth tokens."""

from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path
from typing import Protocol

_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class CredentialStoreError(RuntimeError):
    """Raised when an API credential cannot be read or saved safely."""


class SecretProtector(Protocol):
    """Encrypt and decrypt bytes for the current operating-system user."""

    def protect(self, plaintext: bytes) -> bytes:
        """Encrypt plaintext bytes."""

    def unprotect(self, ciphertext: bytes) -> bytes:
        """Decrypt ciphertext bytes."""


class CredentialStore(Protocol):
    """Persist provider-specific API credentials without exposing plaintext."""

    def get_secret(self, provider: str) -> str | None:
        """Return a saved provider secret, when present."""

    def set_secret(self, provider: str, secret: str) -> None:
        """Encrypt and save a provider secret."""

    def delete_secret(self, provider: str) -> None:
        """Delete a saved provider secret."""

    def get_named_secret(self, namespace: str, name: str) -> str | None:
        """Return one decrypted non-AI secret."""

    def set_named_secret(self, namespace: str, name: str, secret: str) -> None:
        """Encrypt and save one non-AI secret."""

    def delete_named_secret(self, namespace: str, name: str) -> None:
        """Delete one non-AI secret."""


class NamedSecretStore(Protocol):
    """Persist non-AI secrets in an explicit namespace."""

    def get_named_secret(self, namespace: str, name: str) -> str | None:
        """Return one decrypted named secret."""

    def set_named_secret(self, namespace: str, name: str, secret: str) -> None:
        """Encrypt and save one named secret."""

    def delete_named_secret(self, namespace: str, name: str) -> None:
        """Delete one named secret."""


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class WindowsDataProtector:
    """Protect secrets with Windows DPAPI for the current Windows account."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise CredentialStoreError(
                "Encrypted API-key storage requires Windows DPAPI."
            )
        self._crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
        self._crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DataBlob),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        self._crypt32.CryptProtectData.restype = wintypes.BOOL
        self._crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(_DataBlob),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        self._crypt32.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        self._kernel32.LocalFree.restype = wintypes.HLOCAL

    def protect(self, plaintext: bytes) -> bytes:
        """Encrypt bytes with a non-interactive current-user DPAPI call."""
        if not plaintext:
            raise CredentialStoreError("An empty API key cannot be encrypted.")
        input_blob, input_buffer = _build_blob(plaintext)
        output_blob = _DataBlob()
        succeeded = self._crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            "Project Akiha hosted AI credential",
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
        del input_buffer
        if not succeeded:
            raise _windows_error("Windows could not encrypt the API key.")
        return self._copy_and_free(output_blob)

    def unprotect(self, ciphertext: bytes) -> bytes:
        """Decrypt bytes for the same Windows account that encrypted them."""
        if not ciphertext:
            raise CredentialStoreError("The encrypted API key is empty.")
        input_blob, input_buffer = _build_blob(ciphertext)
        output_blob = _DataBlob()
        succeeded = self._crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
        del input_buffer
        if not succeeded:
            raise _windows_error("Windows could not decrypt the saved API key.")
        return self._copy_and_free(output_blob)

    def _copy_and_free(self, blob: _DataBlob) -> bytes:
        try:
            return ctypes.string_at(blob.pbData, blob.cbData)
        finally:
            if blob.pbData:
                self._kernel32.LocalFree(ctypes.cast(blob.pbData, wintypes.HLOCAL))


class EncryptedCredentialStore:
    """Store only DPAPI ciphertext in a small local JSON document."""

    def __init__(
        self,
        path: Path,
        protector: SecretProtector | None = None,
    ) -> None:
        self._path = path
        self._protector = protector or WindowsDataProtector()

    def get_secret(self, provider: str) -> str | None:
        """Return a decrypted provider secret when one is stored."""
        encoded = self._read_entries().get(_credential_name(provider))
        if encoded is None:
            return None
        try:
            ciphertext = base64.b64decode(encoded, validate=True)
            plaintext = self._protector.unprotect(ciphertext)
            return plaintext.decode("utf-8")
        except (ValueError, UnicodeDecodeError, CredentialStoreError) as error:
            raise CredentialStoreError(
                "The saved hosted AI credential could not be decrypted."
            ) from error

    def set_secret(self, provider: str, secret: str) -> None:
        """Encrypt and atomically save a provider secret."""
        normalized = secret.strip()
        if not normalized:
            raise CredentialStoreError("The API key cannot be empty.")
        ciphertext = self._protector.protect(normalized.encode("utf-8"))
        entries = self._read_entries()
        entries[_credential_name(provider)] = base64.b64encode(ciphertext).decode(
            "ascii"
        )
        self._write_entries(entries)

    def delete_secret(self, provider: str) -> None:
        """Delete one provider secret without touching other credentials."""
        entries = self._read_entries()
        removed = entries.pop(_credential_name(provider), None)
        if removed is not None:
            self._write_entries(entries)

    def get_named_secret(self, namespace: str, name: str) -> str | None:
        """Return a decrypted secret outside the legacy AI-key namespace."""
        encoded = self._read_entries().get(_named_secret_name(namespace, name))
        if encoded is None:
            return None
        try:
            ciphertext = base64.b64decode(encoded, validate=True)
            plaintext = self._protector.unprotect(ciphertext)
            return plaintext.decode("utf-8")
        except (ValueError, UnicodeDecodeError, CredentialStoreError) as error:
            raise CredentialStoreError(
                "The saved credential could not be decrypted."
            ) from error

    def set_named_secret(self, namespace: str, name: str, secret: str) -> None:
        """Encrypt and atomically save a namespaced secret."""
        normalized = secret.strip()
        if not normalized:
            raise CredentialStoreError("The credential cannot be empty.")
        ciphertext = self._protector.protect(normalized.encode("utf-8"))
        entries = self._read_entries()
        entries[_named_secret_name(namespace, name)] = base64.b64encode(
            ciphertext
        ).decode("ascii")
        self._write_entries(entries)

    def delete_named_secret(self, namespace: str, name: str) -> None:
        """Delete one namespaced secret without touching other credentials."""
        entries = self._read_entries()
        removed = entries.pop(_named_secret_name(namespace, name), None)
        if removed is not None:
            self._write_entries(entries)

    def _read_entries(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CredentialStoreError(
                "The encrypted credential store could not be read."
            ) from error
        if not isinstance(payload, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in payload.items()
        ):
            raise CredentialStoreError(
                "The encrypted credential store has an invalid format."
            )
        return payload

    def _write_entries(self, entries: dict[str, str]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self._path.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(entries, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary_path.replace(self._path)
        except OSError as error:
            raise CredentialStoreError(
                "The encrypted credential store could not be saved."
            ) from error


def _credential_name(provider: str) -> str:
    normalized = provider.strip().casefold()
    if not normalized:
        raise CredentialStoreError("The AI provider name cannot be empty.")
    return f"ai:{normalized}"


def _named_secret_name(namespace: str, name: str) -> str:
    normalized_namespace = namespace.strip().casefold()
    normalized_name = name.strip().casefold()
    if not normalized_namespace or not normalized_name:
        raise CredentialStoreError("The credential namespace and name are required.")
    if ":" in normalized_namespace or ":" in normalized_name:
        raise CredentialStoreError("Credential names cannot contain a colon.")
    return f"{normalized_namespace}:{normalized_name}"


def _build_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    return _DataBlob(len(data), pointer), buffer


def _windows_error(message: str) -> CredentialStoreError:
    error_code = ctypes.get_last_error()
    return CredentialStoreError(f"{message} Windows error {error_code}.")
