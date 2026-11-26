import secrets
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from threading import Lock

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException

from api.config import AuthSettings


ISSUER = "mobiliza"
AUDIENCE = "mobiliza-api"
LOGIN_LIMIT = 5
INFERENCE_LIMIT = 10
RATE_WINDOW_SECONDS = 60


def unauthorized():
    return HTTPException(401, "Credenciais ou token inválidos", headers={"WWW-Authenticate": "Bearer"})


class RateLimiter:
    """Janela deslizante por processo; somente login global e o usuário configurado."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.events = {}
        self.lock = Lock()

    def allow(self, key, limit):
        now = self.clock()
        with self.lock:
            events = self.events.setdefault(key, deque())
            while events and events[0] <= now - RATE_WINDOW_SECONDS:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            return True


class Authentication:
    def __init__(self, settings: AuthSettings):
        self.settings = settings
        self.hasher = PasswordHasher()
        self.limiter = RateLimiter()

    def login(self, username: str, password: str) -> dict:
        user_matches = secrets.compare_digest(username.encode("utf-8"), self.settings.username.encode("utf-8"))
        try:
            password_matches = self.hasher.verify(self.settings.password_hash, password)
        except (VerificationError, InvalidHashError):
            password_matches = False
        if not (user_matches and password_matches):
            raise unauthorized()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=self.settings.expiration_minutes)
        token = jwt.encode({"sub": self.settings.username, "iss": ISSUER, "aud": AUDIENCE,
                            "iat": now, "exp": expires}, self.settings.jwt_secret, algorithm="HS256")
        return {"access_token": token, "token_type": "bearer",
                "expires_in": self.settings.expiration_minutes * 60}

    def authenticate(self, authorization: str | None) -> str:
        if not authorization or len(authorization) > 4096:
            raise unauthorized()
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token or " " in token:
            raise unauthorized()
        try:
            claims = jwt.decode(token, self.settings.jwt_secret, algorithms=["HS256"],
                                issuer=ISSUER, audience=AUDIENCE,
                                options={"require": ["sub", "iss", "aud", "iat", "exp"]})
            if claims["sub"] != self.settings.username:
                raise unauthorized()
        except jwt.InvalidTokenError:
            raise unauthorized() from None
        return claims["sub"]
