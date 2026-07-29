"""Tests for encrypted hosted AI credential persistence."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.services.credential_store import (
    CredentialStoreError,
    EncryptedCredentialStore,
)


class _TestProtector:
    def protect(self, plaintext: bytes) -> bytes:
        return b"protected:" + plaintext[::-1]

    def unprotect(self, ciphertext: bytes) -> bytes:
        if not ciphertext.startswith(b"protected:"):
            raise CredentialStoreError("Invalid test ciphertext.")
        return ciphertext.removeprefix(b"protected:")[::-1]


class EncryptedCredentialStoreTest(unittest.TestCase):
    """Ensure ordinary local files never receive plaintext API keys."""

    def test_round_trips_encrypted_provider_secrets(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            store = EncryptedCredentialStore(path, protector=_TestProtector())

            store.set_secret("gemini", "  test-api-key  ")

            self.assertEqual(store.get_secret("gemini"), "test-api-key")
            self.assertNotIn("test-api-key", path.read_text(encoding="utf-8"))
            self.assertIsNone(store.get_secret("openai"))

    def test_delete_removes_only_selected_provider(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            store = EncryptedCredentialStore(path, protector=_TestProtector())
            store.set_secret("gemini", "gemini-key")
            store.set_secret("openai", "openai-key")

            store.delete_secret("gemini")

            self.assertIsNone(store.get_secret("gemini"))
            self.assertEqual(store.get_secret("openai"), "openai-key")

    def test_rejects_invalid_store_format(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
            store = EncryptedCredentialStore(path, protector=_TestProtector())

            with self.assertRaises(CredentialStoreError):
                store.get_secret("gemini")

    def test_rejects_empty_provider_and_secret(self) -> None:
        with TemporaryDirectory() as directory:
            store = EncryptedCredentialStore(
                Path(directory) / "credentials.json",
                protector=_TestProtector(),
            )

            with self.assertRaises(CredentialStoreError):
                store.set_secret("gemini", " ")
            with self.assertRaises(CredentialStoreError):
                store.get_secret(" ")


if __name__ == "__main__":
    unittest.main()
