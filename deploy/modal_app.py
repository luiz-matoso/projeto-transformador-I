import os
from pathlib import Path

import modal


ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "mobiliza-transitability"
VOLUME_NAME = os.getenv("MOBILIZA_MODAL_VOLUME", "mobiliza-models")
GPU = os.getenv("MOBILIZA_MODAL_GPU") or None

image = modal.Image.debian_slim(python_version="3.13")
if GPU is None:
    image = image.pip_install("torch==2.14.0+cpu", "torchvision==0.29.0+cpu", index_url="https://download.pytorch.org/whl/cpu")
else:
    image = image.pip_install("torch==2.14.0+cu130", "torchvision==0.29.0+cu130", index_url="https://download.pytorch.org/whl/cu130")
image = (
    image.pip_install_from_requirements(str(ROOT / "requirements-api.txt"))
    .env({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
          "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "TOKENIZERS_PARALLELISM": "false"})
    .add_local_python_source("deploy", "api", "ml", copy=True)
    .add_local_file(ROOT / "requirements-api.txt", "/root/requirements-api.txt", copy=True)
    .run_commands("python -m pip check", "python /root/deploy/verify_runtime.py" + (" --cpu" if GPU is None else ""))
)
volume = modal.Volume.from_name(VOLUME_NAME)
app = modal.App(APP_NAME)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("mobiliza-auth", required_keys=["AUTH_USERNAME", "AUTH_PASSWORD_HASH", "JWT_SECRET", "JWT_EXPIRATION_MINUTES"])],
    volumes={"/models": volume.with_mount_options(read_only=True)},
    cpu=2,
    memory=4096,
    gpu=GPU,
    min_containers=0,
    max_containers=1,
    scaledown_window=30,
    timeout=300,
    startup_timeout=300,
    include_source=False,
    env={"MOBILIZA_SEGFORMER_CHECKPOINT": "/models/segformer/best_segformer.pt",
         "MOBILIZA_DINO_CHECKPOINT": "/models/dinov2/best_dinov2_v2.pt",
         "MOBILIZA_DEVICE": "cuda" if GPU else "cpu",
         "MOBILIZA_CORS_ORIGINS": os.getenv("MOBILIZA_CORS_ORIGINS", ""),
         "MOBILIZA_MAX_CONCURRENCY": "1"},
)
@modal.concurrent(max_inputs=2, target_inputs=1)
@modal.asgi_app()
def serve():
    from api.main import app as fastapi_app

    return fastapi_app
