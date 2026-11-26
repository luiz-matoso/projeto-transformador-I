import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from packaging.requirements import Requirement


def main():
    parser = argparse.ArgumentParser(description="Verifica versões e compatibilidade estrita de inferência")
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    installed = {}
    for line in (Path(__file__).resolve().parents[1] / "requirements-api.txt").read_text().splitlines():
        if not line or line.startswith(("#", "--")):
            continue
        requirement = Requirement(line)
        actual = version(requirement.name)
        if actual not in requirement.specifier:
            raise RuntimeError(f"Versão incompatível: {requirement.name}={actual}; esperado {requirement.specifier}")
        installed[requirement.name] = actual
    import torch
    from transformers import Dinov2Config, Dinov2Model

    if args.cpu and (torch.version.cuda is not None or not version("torch").endswith("+cpu") or not version("torchvision").endswith("+cpu")):
        raise RuntimeError("O ambiente deve utilizar wheels CPU de torch e torchvision")
    tiny = Dinov2Model(Dinov2Config(hidden_size=16, num_hidden_layers=1, num_attention_heads=4))
    key = "encoder.layer.0.attention.attention.query.weight"
    if key not in tiny.state_dict():
        raise RuntimeError("Estrutura DINO incompatível com as chaves do checkpoint")
    del tiny
    report = {"python": platform.python_version(), "platform": platform.platform(),
              "packages": installed, "cpu_wheels": torch.version.cuda is None, "dino_query_key": key}
    if args.bundle:
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from api.config import Settings
        from api.main import create_app

        import os
        import secrets
        from argon2 import PasswordHasher
        password = secrets.token_urlsafe(24)
        auth_env = {"AUTH_USERNAME": "runtime-validation", "AUTH_PASSWORD_HASH": PasswordHasher().hash(password),
                    "JWT_SECRET": secrets.token_urlsafe(48), "JWT_EXPIRATION_MINUTES": "120"}
        bundle = args.bundle.resolve()
        settings = Settings(segformer_checkpoint=bundle / "segformer/best_segformer.pt",
                            dino_checkpoint=bundle / "dinov2/best_dinov2_v2.pt", device="cpu")
        paths = (settings.segformer_checkpoint, settings.dino_checkpoint)
        hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        metadata = {"profiles": [{"minimum_passage_width": "adequate", "surface_tolerance": "minor_problems",
                                  "level_change_tolerance": "minor", "accepts_partial_obstruction": True}],
                    "observation": {"source": "runtime_validation_simulated_timestamp", "observed_at": datetime.now(timezone.utc).isoformat()}}
        image = Path("data/annotation-pilot/images/curb_ramp/gsv-amsterdam-18384-CurbRamp.png")
        with patch.dict(os.environ, auth_env), patch("transformers.AutoModel.from_pretrained", side_effect=AssertionError("Download de pesos-base não permitido")), TestClient(create_app(settings)) as client:
            health = client.get("/health")
            if health.status_code != 200:
                raise RuntimeError(f"Falha no carregamento estrito: {health.text}")
            login = client.post("/auth/login", json={"username": auth_env["AUTH_USERNAME"], "password": password})
            if login.status_code != 200:
                raise RuntimeError("Falha na autenticação de integração")
            client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
            with image.open("rb") as handle:
                response = client.post("/transitability", data={"metadata": json.dumps(metadata)}, files={"image": (image.name, handle, "image/png")})
            if response.status_code != 200 or response.json()["mask"] is None:
                raise RuntimeError(f"Falha de inferência: {response.status_code} {response.text[:500]}")
            result = response.json()
        if hashes != {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}:
            raise RuntimeError("Checkpoint alterado")
        report.update(checkpoints_loaded_strictly=True, checkpoint_hashes=hashes,
                      authentication_verified=True, inference_device="cpu", classification=result["assessments"][0]["classification"],
                      timestamp_simulated=True, model_download_disabled=True)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
