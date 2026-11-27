import asyncio
import json
import os
import time
import unittest
from unittest.mock import AsyncMock, patch

import jwt
import numpy as np
from fastapi.testclient import TestClient

from api.auth import AUDIENCE, ISSUER, INFERENCE_LIMIT, LOGIN_LIMIT, RateLimiter
from api.config import AuthSettings, Settings
from api.main import create_app
from tests.test_api import AUTH_ENV, TEST_PASSWORD, image_bytes, metadata


class AuthTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, AUTH_ENV)
        environment.start()
        self.addCleanup(environment.stop)
        loader = patch("api.main.load_components", return_value=(None, None, None, None, "cpu", {}))
        self.load = loader.start()
        self.addCleanup(loader.stop)
        self.app = create_app(Settings(cors_origins=("https://mobiliza.example",)))
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def login(self, **kwargs):
        return self.client.post("/auth/login", json={"username": AUTH_ENV["AUTH_USERNAME"],
                                                   "password": TEST_PASSWORD, **kwargs})

    def token(self, **claims):
        now = int(time.time())
        return jwt.encode({"sub": AUTH_ENV["AUTH_USERNAME"], "iss": ISSUER, "aud": AUDIENCE,
                           "iat": now, "exp": now + 7200, **claims}, AUTH_ENV["JWT_SECRET"], algorithm="HS256")

    def test_valid_login_and_configurable_expiration(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        data = response.json()
        self.assertEqual(data["token_type"], "bearer")
        self.assertEqual(data["expires_in"], 7200)
        claims = jwt.decode(data["access_token"], AUTH_ENV["JWT_SECRET"], algorithms=["HS256"], audience=AUDIENCE)
        self.assertEqual(claims["exp"] - claims["iat"], 7200)
        self.app.state.auth.settings = AuthSettings(**{**vars(self.app.state.auth.settings), "expiration_minutes": 5})
        self.assertEqual(self.login().json()["expires_in"], 300)

    def test_invalid_credentials_have_same_generic_401(self):
        for payload in ({"username": "unknown"}, {"password": "incorrect"}):
            response = self.login(**payload)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers["www-authenticate"], "Bearer")
            self.assertNotIn(TEST_PASSWORD, response.text)
            self.assertNotIn("access_token", response.json())

    def test_malformed_login_does_not_echo_password(self):
        response = self.client.post("/auth/login", json={"password": TEST_PASSWORD})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(TEST_PASSWORD, response.text)
        response = self.client.post("/auth/login", content=b"x" * 4097)
        self.assertEqual(response.status_code, 413)

    def test_missing_token_rejected_without_reading_body(self):
        receive, send = AsyncMock(), AsyncMock()
        scope = {"type": "http", "asgi": {"version": "3.0"}, "method": "POST",
                 "scheme": "https", "path": "/transitability", "raw_path": b"/transitability",
                 "query_string": b"", "headers": [], "server": ("test", 443),
                 "client": ("test", 123), "root_path": ""}
        asyncio.run(self.app(scope, receive, send))
        receive.assert_not_awaited()
        self.assertEqual(send.await_args_list[0].args[0]["status"], 401)

    def test_expired_tampered_and_invalid_tokens(self):
        token = self.token()
        header, payload, signature = token.split(".")
        tampered = ".".join((header, payload, ("A" if signature[0] != "A" else "B") + signature[1:]))
        tokens = [self.token(exp=int(time.time()) - 1), tampered, "invalid", self.token(sub="another"),
                  self.token(aud="other"), self.token(iss="other"), self.token(iat=int(time.time()) + 1000),
                  jwt.encode({"sub": AUTH_ENV["AUTH_USERNAME"]}, AUTH_ENV["JWT_SECRET"], algorithm="HS256")]
        for token in tokens:
            with self.subTest(token_case=tokens.index(token)):
                response = self.client.post("/transitability", headers={"Authorization": "Bearer " + token})
                self.assertEqual(response.status_code, 401)
        none_token = jwt.encode({"sub": AUTH_ENV["AUTH_USERNAME"], "exp": int(time.time()) + 100}, key="", algorithm="none")
        self.assertEqual(self.client.post("/transitability", headers={"Authorization": "Bearer " + none_token}).status_code, 401)

    def test_authorized_request_reaches_pipeline(self):
        observed = {"mask": np.ones((16, 24), dtype=np.uint8), "features": {
            "passage_width": "adequate", "obstruction": "none", "surface_condition": "regular",
            "level_change": "none", "path_continuity": "continuous"}, "predictions": {},
            "not_modeled": {}, "inactive_features": []}
        with patch("api.routes.transitability.observe_scene",
                   side_effect=lambda image, observation, components: {**observed, "observation": observation}) as vision:
            response = self.client.post("/transitability", headers={"Authorization": "Bearer " + self.token()},
                                        data={"metadata": json.dumps(metadata())},
                                        files={"image": ("test.png", image_bytes(), "image/png")})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["assessments"][0]["classification"], "transitable")
        vision.assert_called_once()

    def test_login_rate_limit_is_global_and_resets_with_controlled_time(self):
        clock = [100.0]
        self.app.state.auth.limiter = RateLimiter(clock=lambda: clock[0])
        for _ in range(LOGIN_LIMIT):
            self.assertEqual(self.login(password="incorrect").status_code, 401)
        response = self.login()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "60")
        clock[0] += 60
        self.assertEqual(self.login().status_code, 200)

    def test_inference_limit_cannot_be_bypassed_by_logging_in_again(self):
        # Authenticated malformed requests count too, before multipart parsing.
        for _ in range(INFERENCE_LIMIT):
            response = self.client.post("/transitability", headers={"Authorization": "Bearer " + self.token()})
            self.assertEqual(response.status_code, 422)
        fresh_token = self.login().json()["access_token"]
        response = self.client.post("/transitability", headers={"Authorization": "Bearer " + fresh_token})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_health_public_and_cors_accepts_authorization(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        body = self.client.get("/health").text
        for value in AUTH_ENV.values():
            if len(value) > 10:
                self.assertNotIn(value, body)
        response = self.client.options("/transitability", headers={"Origin": "https://mobiliza.example",
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Authorization"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Authorization", response.headers["access-control-allow-headers"])
        schema = self.client.get("/openapi.json").json()
        self.assertIn("HTTPBearer", schema["components"]["securitySchemes"])

    def test_missing_config_fails_before_loading_models(self):
        with patch.dict(os.environ, {}, clear=True):
            for name in ("AUTH_USERNAME", "AUTH_PASSWORD_HASH", "JWT_SECRET"):
                with patch.dict(os.environ, {key: value for key, value in AUTH_ENV.items() if key != name}, clear=True):
                    with self.assertRaisesRegex(RuntimeError, "Configuração de autenticação"):
                        with TestClient(create_app()):
                            pass
        self.assertEqual(self.load.call_count, 1)

    def test_invalid_auth_configuration_and_no_secret_repr(self):
        for values in ({"JWT_SECRET": "short"}, {"AUTH_PASSWORD_HASH": "invalid"},
                       {"AUTH_USERNAME": ""}, {"JWT_EXPIRATION_MINUTES": "0"},
                       {"JWT_EXPIRATION_MINUTES": "bad"}):
            with patch.dict(os.environ, {**AUTH_ENV, **values}):
                with self.assertRaises(RuntimeError):
                    AuthSettings.from_env()
        self.assertNotIn(AUTH_ENV["JWT_SECRET"], repr(AuthSettings.from_env()))
        self.assertNotIn(AUTH_ENV["AUTH_PASSWORD_HASH"], repr(AuthSettings.from_env()))


if __name__ == "__main__":
    unittest.main()
