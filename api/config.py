from dataclasses import dataclass
from pathlib import Path
from starlette.config import Config

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"

def environment() -> Config:
    """Process variables override the optional local .env file."""
    return Config(ENV_FILE if ENV_FILE.is_file() else None, encoding="utf-8-sig")


@dataclass(frozen=True)
class Settings:
    segformer_checkpoint: Path = Path(".modal-models/segformer/best_segformer.pt")
    dino_checkpoint: Path = Path(".modal-models/dinov2/best_dinov2_v2.pt")
    device: str | None = "cpu"
    cors_origins: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")
    max_image_bytes: int = 8 * 1024 * 1024
    max_pixels: int = 8_000_000
    max_dimension: int = 8192
    max_concurrency: int = 1

    def __post_init__(self):
        for name in ("max_image_bytes", "max_pixels", "max_dimension", "max_concurrency"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} deve ser positivo")
        if self.device not in (None, "cpu", "cuda"):
            raise ValueError("MOBILIZA_DEVICE deve ser cpu ou cuda")

    @classmethod
    def from_env(cls):
        env = environment()
        return cls(
            segformer_checkpoint=Path(env("MOBILIZA_SEGFORMER_CHECKPOINT", default=str(cls.segformer_checkpoint))),
            dino_checkpoint=Path(env("MOBILIZA_DINO_CHECKPOINT", default=str(cls.dino_checkpoint))),
            device=env("MOBILIZA_DEVICE", default=cls.device) or None,
            cors_origins=tuple(x.strip() for x in env("MOBILIZA_CORS_ORIGINS", default=",".join(cls.cors_origins)).split(",") if x.strip()),
            **{name: env("MOBILIZA_" + name.upper(), cast=int, default=getattr(cls, name))
               for name in ("max_image_bytes", "max_pixels", "max_dimension", "max_concurrency")},
        )


@dataclass(frozen=True, repr=False)
class AuthSettings:
    username: str
    password_hash: str
    jwt_secret: str
    expiration_minutes: int = 120

    def __post_init__(self):
        from argon2 import extract_parameters, Type
        try:
            valid_hash = extract_parameters(self.password_hash).type == Type.ID
        except Exception:
            valid_hash = False
        if (not self.username.strip() or not valid_hash or
                len(self.jwt_secret.encode("utf-8")) < 32 or self.expiration_minutes <= 0):
            raise ValueError("Configuração de autenticação ausente ou inválida")

    @classmethod
    def from_env(cls):
        env = environment()
        try:
            return cls(username=env("AUTH_USERNAME", default=""),
                       password_hash=env("AUTH_PASSWORD_HASH", default=""),
                       jwt_secret=env("JWT_SECRET", default=""),
                       expiration_minutes=env("JWT_EXPIRATION_MINUTES", cast=int, default=120))
        except (KeyError, ValueError):
            raise RuntimeError("Configuração de autenticação ausente ou inválida") from None
