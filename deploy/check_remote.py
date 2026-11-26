import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description="Verifica health e uma inferência remota com metadados explícitos")
    parser.add_argument("--url", required=True)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    args = parser.parse_args()
    url = args.url.rstrip("/")
    with urlopen(url + "/health", timeout=300) as response:
        health = json.load(response)
    if not health.get("models_loaded"):
        raise SystemExit(f"Modelos indisponíveis: {health}")
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    image = args.image.read_bytes()
    media_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}[args.image.suffix.lower()]
    boundary = uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n'.encode()
            + json.dumps(metadata).encode() + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="image"\r\nContent-Type: {media_type}\r\n\r\n'.encode()
            + image + f"\r\n--{boundary}--\r\n".encode())
    request = Request(url + "/transitability", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urlopen(request, timeout=300) as response:
            result = json.load(response)
    except HTTPError as error:
        raise SystemExit(f"HTTP {error.code}: {error.read().decode()}") from error
    if len(result["assessments"]) != len(metadata["profiles"]):
        raise SystemExit("Quantidade de avaliações inesperada")
    print(json.dumps({"health": health, "observation": result["observation"],
                      "classifications": [a["classification"] for a in result["assessments"]],
                      "mask_received": result["mask"] is not None}, indent=2, ensure_ascii=False))
    if not result["observation"]["is_valid"] or result["mask"] is None:
        raise SystemExit("Requisição temporalmente inválida: teste não confirmou inferência visual")


if __name__ == "__main__":
    main()
