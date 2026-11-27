import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    segformer_checkpoint: Path = Path("artifacts/segmentation/common-dino-split/best_segformer.pt")
    dino_checkpoint: Path = Path("artifacts/dinov2/v2/partial/best_dinov2_v2.pt")
    device: str | None = None
    cors_origins: tuple[str, ...] = ()
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
        return cls(
            segformer_checkpoint=Path(os.getenv("MOBILIZA_SEGFORMER_CHECKPOINT", str(cls.segformer_checkpoint))),
            dino_checkpoint=Path(os.getenv("MOBILIZA_DINO_CHECKPOINT", str(cls.dino_checkpoint))),
            device=os.getenv("MOBILIZA_DEVICE") or None,
            cors_origins=tuple(x.strip() for x in os.getenv("MOBILIZA_CORS_ORIGINS", "").split(",") if x.strip()),
            **{name: int(os.getenv("MOBILIZA_" + name.upper(), str(getattr(cls, name))))
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
        try:
            return cls(username=os.environ["AUTH_USERNAME"],
                       password_hash=os.environ["AUTH_PASSWORD_HASH"],
                       jwt_secret=os.environ["JWT_SECRET"],
                       expiration_minutes=int(os.getenv("JWT_EXPIRATION_MINUTES", "120")))
        except (KeyError, ValueError):
            raise RuntimeError("Configuração de autenticação ausente ou inválida") from None
