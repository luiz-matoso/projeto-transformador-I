"""Opt-in check against a configured API/Supabase. Uses real inference, removes its own records."""
import argparse
import base64
import getpass
import json
import mimetypes
from pathlib import Path
from uuid import uuid4
import httpx


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url",required=True)
    parser.add_argument("--username",required=True)
    parser.add_argument("--image",type=Path,required=True)
    parser.add_argument("--metadata",type=Path,required=True)
    args=parser.parse_args()
    payload=json.loads(args.metadata.read_text(encoding="utf-8"))
    if len(payload["profiles"]) != 2:
        parser.error("Metadata precisa conter exatamente dois perfis")
    image=args.image.read_bytes()
    mime=mimetypes.guess_type(args.image.name)[0] or "image/png"
    profiles=[{"id":str(uuid4()),"name":"Persistence check " + str(uuid4()),"requirements":r} for r in payload["profiles"]]
    identifier=str(uuid4())
    with httpx.Client(base_url=args.url.rstrip("/"),timeout=300) as api:
        response=api.post("/auth/login",json={"username":args.username,"password":getpass.getpass("Demonstration password: ")})
        response.raise_for_status()
        api.headers["Authorization"]="Bearer "+response.json()["access_token"]
        try:
            for profile in profiles:
                api.post("/profiles",json=profile).raise_for_status()
            response=api.post("/transitability",data={"metadata":json.dumps(payload)},files={"image":(args.image.name,image,mime)})
            response.raise_for_status();result=response.json()
            metadata={"id":identifier,"profiles":profiles,"result":result}
            for _ in range(2):
                api.post("/analyses",data={"metadata":json.dumps(metadata)},files={"image":(args.image.name,image,mime)}).raise_for_status()
            response=api.get("/analyses/"+identifier);response.raise_for_status();detail=response.json()
            with httpx.Client(timeout=30) as storage:
                original=storage.get(detail["image_url"]);original.raise_for_status();assert original.content==image
                if result["mask"]:
                    mask=storage.get(detail["mask_url"]);mask.raise_for_status();assert mask.content==base64.b64decode(result["mask"]["data"])
                else:
                    assert detail["mask_url"] is None
            edited={**profiles[0],"name":profiles[0]["name"]+" edited"}
            api.put("/profiles/"+edited["id"],json=edited).raise_for_status()
            historical=api.get("/analyses/"+identifier);historical.raise_for_status()
            assert historical.json()["profiles"][0]["name"]==profiles[0]["name"]
            print("PASS: CRUD, upload/download privado, snapshot, retry idempotente e histórico sem nova inferência.")
        finally:
            api.delete("/analyses/"+identifier).raise_for_status()
            for profile in profiles:
                api.delete("/profiles/"+profile["id"]).raise_for_status()
        assert api.get("/analyses/"+identifier).status_code==404
        print("PASS: registros de verificação e arquivos excluídos.")

if __name__=="__main__":
    try:
        main()
    except httpx.HTTPError:
        raise SystemExit("Verificação HTTP falhou. Confira a configuração e tente novamente; nenhum token foi exibido.") from None
