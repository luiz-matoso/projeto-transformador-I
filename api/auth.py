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


def initialize_local_auth(env_file=None):
    """Fill local auth settings without exposing or storing the password."""
    import getpass
    import os
    import re
    import tempfile
    from pathlib import Path
    from starlette.config import Config
    from api.config import ENV_FILE

    target = Path(env_file) if env_file is not None else ENV_FILE
    if not target.is_file():
        raise ValueError("Copie .env.example para .env antes de inicializar o acesso")
    local = Config(target, environ={}, encoding="utf-8-sig")
    if local("AUTH_PASSWORD_HASH", default="") or local("JWT_SECRET", default=""):
        raise ValueError("O .env já possui credenciais; a configuração existente foi preservada")
    username = input("Usuário: ").strip()
    if not username or any(c in username for c in "\r\n='\"#"):
        raise ValueError("Informe um usuário sem aspas, # ou sinal de igual")
    password = getpass.getpass("Senha: ")
    confirm = getpass.getpass("Confirme a senha: ")
    if not password or password != confirm:
        raise ValueError("As senhas precisam ser iguais e não vazias")
    values = {"AUTH_USERNAME": username, "AUTH_PASSWORD_HASH": PasswordHasher().hash(password),
              "JWT_SECRET": secrets.token_urlsafe(48)}
    text = target.read_text(encoding="utf-8-sig")
    for key, value in values.items():
        pattern = r"^\s*" + key + r"\s*=.*$"
        if re.search(pattern, text, flags=re.MULTILINE):
            text = re.sub(pattern, lambda match: key + "=" + value, text, flags=re.MULTILINE)
        else:
            text = text.rstrip() + "\n" + key + "=" + value + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".env.", dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        temporary.chmod(0o600)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Configuração local de autenticação do Permear")
    parser.add_argument("command", choices=("init",))
    parser.parse_args()
    try:
        initialize_local_auth()
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + "\n")
    print("Acesso configurado no .env. A senha não foi armazenada.")
