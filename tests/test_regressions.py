import argparse
import importlib
import io
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def import_fresh(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


class ValidateConfigRegressionTests(unittest.TestCase):
    def test_validate_config_flags_schema_violations(self):
        validate_config = import_fresh("validate_config")

        config = {
            "schema_version": "1.0",
            "notification_channels": {
                "telegram": {
                    "bot_token": "token",
                    "chat_id": "chat",
                }
            },
            "characters": [
                {
                    "id": "not-an-int",
                    "token": "token",
                    "refresh_token": "refresh",
                    "client_id": "client",
                    "scopes": ["esi-wallet.read_character_wallet.v1"],
                }
            ],
            "alerts": {
                "channels": ["slack"],
            },
            "unexpected_top_level": True,
        }

        result = validate_config.validate_config(config)

        self.assertTrue(
            any("unexpected_top_level" in error for error in result.errors),
            result.errors,
        )
        self.assertTrue(
            any("alerts.channels[0]" in error for error in result.errors),
            result.errors,
        )
        self.assertTrue(
            any("characters[0].id" in error for error in result.errors),
            result.errors,
        )

    def test_validate_scope_coverage_respects_character_filter(self):
        validate_config = import_fresh("validate_config")

        config = {
            "schema_version": "1.0",
            "notification_channels": {
                "telegram": {
                    "bot_token": "token",
                    "chat_id": "chat",
                }
            },
            "characters": [
                {
                    "id": 1,
                    "name": "A",
                    "token": "token",
                    "refresh_token": "refresh",
                    "client_id": "client",
                    "scopes": ["esi-wallet.read_character_wallet.v1"],
                },
                {
                    "id": 2,
                    "name": "B",
                    "token": "token",
                    "refresh_token": "refresh",
                    "client_id": "client",
                    "scopes": ["esi-skills.read_skills.v1"],
                },
            ],
            "alerts": {
                "rules": [
                    {
                        "type": "wallet_large_deposit",
                        "character_filter": [1],
                    }
                ]
            },
        }

        result = validate_config.validate_config(config)

        self.assertFalse(
            any("Character 'B'" in warning for warning in result.warnings),
            result.warnings,
        )


class TokenStoreRegressionTests(unittest.TestCase):
    def test_save_tokens_waits_for_existing_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["OPENCLAW_STATE_DIR"] = tmpdir
            token_store = import_fresh("token_store")

            finished = threading.Event()

            def writer():
                try:
                    token_store.save_tokens({"characters": {"main": {"refresh_token": "r"}}})
                finally:
                    finished.set()

            with token_store.token_file_lock():
                thread = threading.Thread(target=writer)
                thread.start()
                time.sleep(0.2)
                self.assertFalse(finished.is_set(), "save_tokens should wait for lock release")

            thread.join(timeout=1.0)
            self.assertTrue(finished.is_set(), "save_tokens should finish after lock release")


class AuthFlowRegressionTests(unittest.TestCase):
    def test_main_wraps_server_start_errors(self):
        auth_flow = import_fresh("auth_flow")

        with mock.patch.object(sys, "argv", ["auth_flow.py", "--client-id", "client"]):
            with mock.patch.object(
                auth_flow.http.server,
                "HTTPServer",
                side_effect=OSError("Address already in use"),
            ):
                with self.assertRaises(auth_flow.AuthFlowError):
                    auth_flow.main()


class GetTokenRegressionTests(unittest.TestCase):
    def test_main_raises_token_error_for_incomplete_character_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["OPENCLAW_STATE_DIR"] = tmpdir
            get_token = import_fresh("get_token")
            token_file = Path(tmpdir) / "eve-tokens.json"
            token_file.write_text(
                '{"characters":{"main":{"character_id":1,"character_name":"Main"}}}',
                encoding="utf-8",
            )

            with mock.patch.object(sys, "argv", ["get_token.py", "--char", "main"]):
                with self.assertRaises(get_token.TokenError):
                    get_token.main()


class EsiQueryWriteGateTests(unittest.TestCase):
    """State-changing requests must not run without an explicit opt-in."""

    def setUp(self):
        self.esi_query = import_fresh("esi_query")

    def test_get_is_never_state_changing(self):
        self.assertFalse(self.esi_query.is_state_changing("GET", "/characters/1/wallet/"))

    def test_documented_bulk_lookups_are_not_state_changing(self):
        for endpoint in (
            "/universe/names/",
            "/characters/affiliation/",
            "/characters/12345/assets/names/",
            "/characters/12345/assets/locations/",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertFalse(self.esi_query.is_state_changing("POST", endpoint))

    def test_undocumented_post_put_delete_are_state_changing(self):
        for method, endpoint in (
            ("POST", "/characters/12345/contacts/"),
            ("POST", "/ui/openwindow/marketdetails/"),
            ("PUT", "/characters/12345/mail/1/"),
            ("DELETE", "/characters/12345/mail/1/"),
        ):
            with self.subTest(method=method, endpoint=endpoint):
                self.assertTrue(self.esi_query.is_state_changing(method, endpoint))

    def test_main_refuses_write_without_allow_write(self):
        argv = [
            "esi_query.py", "--token", "tok",
            "--endpoint", "/characters/12345/contacts/",
            "--method", "POST", "--body", "[]",
        ]
        with mock.patch.object(sys, "argv", argv):
            with mock.patch.object(self.esi_query, "esi_request") as request:
                with self.assertRaises(SystemExit):
                    self.esi_query.main()
                request.assert_not_called()

    def test_lookalike_endpoint_does_not_bypass_gate(self):
        # A path merely containing a read-only segment must still be gated.
        self.assertTrue(
            self.esi_query.is_state_changing("POST", "/characters/affiliation/evil/")
        )


class EsiQueryTokenSourceTests(unittest.TestCase):
    """The token must be resolvable without ever landing in argv."""

    def setUp(self):
        self.esi_query = import_fresh("esi_query")

    def _args(self, **overrides):
        defaults = {"char": None, "token": None, "token_stdin": False}
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_token_stdin_is_read_from_stdin(self):
        parser = argparse.ArgumentParser()
        with mock.patch.object(sys, "stdin", io.StringIO("secret-token\n")):
            token = self.esi_query.resolve_token(self._args(token_stdin=True), parser)
        self.assertEqual(token, "secret-token")

    def test_char_resolves_in_process(self):
        parser = argparse.ArgumentParser()
        fake = mock.Mock(return_value={"access_token": "fresh-token"})
        with mock.patch.dict(sys.modules, {"get_token": mock.Mock(resolve_access_token=fake)}):
            token = self.esi_query.resolve_token(self._args(char="main"), parser)
        self.assertEqual(token, "fresh-token")
        fake.assert_called_once_with("main")

    def test_conflicting_token_sources_are_rejected(self):
        parser = argparse.ArgumentParser()
        with mock.patch.object(sys, "stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                self.esi_query.resolve_token(self._args(char="main", token="tok"), parser)

    def test_argv_token_warns_about_exposure(self):
        parser = argparse.ArgumentParser()
        stderr = io.StringIO()
        with mock.patch.object(sys, "stderr", stderr):
            token = self.esi_query.resolve_token(self._args(token="tok"), parser)
        self.assertEqual(token, "tok")
        self.assertIn("argv", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
