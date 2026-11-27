import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from starlette.config import Config
from argon2 import PasswordHasher
from api.config import Settings, AuthSettings
from api.auth import initialize_local_auth
from api.storage import WorkspaceStorage


class LocalConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / ".env"
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        location = patch("api.config.ENV_FILE", self.path)
        location.start()
        self.addCleanup(location.stop)

    def init(self, password="local-test-password"):
        self.path.write_text("# Preserve comments\nAUTH_USERNAME=\nAUTH_PASSWORD_HASH=\nJWT_SECRET=\nMOBILIZA_DEVICE=cpu\nSUPABASE_URL=\nSUPABASE_SECRET_KEY=\n", encoding="utf-8")
        with patch("builtins.input", return_value="local-test"), patch("getpass.getpass", side_effect=[password, password]):
            initialize_local_auth(self.path)

    def test_safe_local_defaults_without_file(self):
        settings = Settings.from_env()
        self.assertEqual(settings.device, "cpu")
        self.assertEqual(settings.dino_checkpoint, Path(".modal-models/dinov2/best_dinov2_v2.pt"))
        self.assertIn("http://127.0.0.1:5173", settings.cors_origins)
        with self.assertRaises(RuntimeError):
            AuthSettings.from_env()
        self.assertIsNone(WorkspaceStorage.from_env())

    def test_init_generates_hash_and_secret_preserving_other_values(self):
        self.init()
        text = self.path.read_text()
        self.assertNotIn("local-test-password", text)
        self.assertIn("# Preserve comments", text)
        self.assertIn("MOBILIZA_DEVICE=cpu", text)
        settings = AuthSettings.from_env()
        self.assertEqual(settings.username, "local-test")
        self.assertTrue(PasswordHasher().verify(settings.password_hash, "local-test-password"))
        self.assertGreaterEqual(len(settings.jwt_secret), 32)
        self.assertEqual(settings.expiration_minutes, 120)

    def test_process_environment_has_priority(self):
        self.init()
        with patch.dict(os.environ, {"AUTH_USERNAME":"environment-user", "MOBILIZA_DEVICE":"cuda", "JWT_EXPIRATION_MINUTES":"5"}):
            self.assertEqual(AuthSettings.from_env().username, "environment-user")
            self.assertEqual(AuthSettings.from_env().expiration_minutes, 5)
            self.assertEqual(Settings.from_env().device, "cuda")
        self.assertEqual(AuthSettings.from_env().username, "local-test")

    def test_init_does_not_overwrite_configured_credentials(self):
        self.init()
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            initialize_local_auth(self.path)
        self.assertEqual(self.path.read_bytes(), original)

    def test_mismatched_passwords_leave_file_unchanged(self):
        self.path.write_text("AUTH_PASSWORD_HASH=\nJWT_SECRET=\n", encoding="utf-8")
        original = self.path.read_bytes()
        with patch("builtins.input", return_value="local-test"), patch("getpass.getpass", side_effect=["one", "two"]):
            with self.assertRaises(ValueError):
                initialize_local_auth(self.path)
        self.assertEqual(self.path.read_bytes(), original)

    def test_supabase_settings_are_loaded_from_file(self):
        self.path.write_text("SUPABASE_URL=https://isolated.example\nSUPABASE_SECRET_KEY=sb_secret_test_only\n", encoding="utf-8")
        store = WorkspaceStorage.from_env()
        self.assertEqual(store.url, "https://isolated.example")
        self.assertEqual(store.client.headers["apikey"], "sb_secret_test_only")
        asyncio.run(store.close())

    def test_invalid_configuration_remains_fail_closed(self):
        self.path.write_text("AUTH_USERNAME=test\nAUTH_PASSWORD_HASH=invalid\nJWT_SECRET=short\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            AuthSettings.from_env()
