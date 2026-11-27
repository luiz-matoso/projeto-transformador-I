"""Validação local real do Workspace; não utiliza ou publica credenciais de produção."""
import csv
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from argon2 import PasswordHasher
from scripts.export_workspace_data import ROOT
from tools.annotation_app.core import load_annotations, load_schema


def create_validation_app():
    """Real ML/API; Supabase HTTP is explicitly replaced ONLY in this local test server."""
    import httpx
    from contextlib import asynccontextmanager
    from fastapi import Response
    from api.main import create_app
    from api.storage import WorkspaceStorage
    from tests.workspace_fake import SupabaseFake
    app = create_app()
    lifespan = app.router.lifespan_context
    @asynccontextmanager
    async def validation_lifespan(application):
        async with lifespan(application):
            original = application.state.storage
            application.state.storage = WorkspaceStorage("https://supabase.test", "sb_secret_test_only", transport=httpx.MockTransport(fake))
            try:
                yield
            finally:
                await application.state.storage.close()
                application.state.storage = original
    app.router.lifespan_context = validation_lifespan
    @app.get("/validation-assets/{key:path}", include_in_schema=False)
    async def asset(key: str, token: str):
        from fastapi import HTTPException
        if token != "test-only" or key not in fake.objects:
            raise HTTPException(404)
        content, mime = fake.objects[key]
        return Response(content, media_type=mime)
    original_call = SupabaseFake.__call__
    # Signed URLs refer to the local, isolated test server; production uses Supabase URLs.
    class LocalFake(SupabaseFake):
        def __call__(self, request):
            response = original_call(self, request)
            if request.url.path.startswith("/storage/v1/object/sign/"):
                key=request.url.path.removeprefix("/storage/v1/object/sign/")
                return httpx.Response(200,json={"signedURL":"http://127.0.0.1:8765/validation-assets/"+key+"?token=test-only"})
            return response
    fake = LocalFake()
    return app


def main():
    evidence = Path(os.getenv("WORKSPACE_EVIDENCE_DIR", str(ROOT / "artifacts/workspace-persistence"))).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    image = ROOT / "data/annotation-pilot/images/curb_ramp/gsv-amsterdam-18384-CurbRamp.png"
    checkpoints = [ROOT / ".modal-models/segformer/best_segformer.pt", ROOT / ".modal-models/dinov2/best_dinov2_v2.pt"]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in checkpoints}
    password = secrets.token_urlsafe(32)
    env = {**os.environ, "AUTH_USERNAME": "workspace-validation", "AUTH_PASSWORD_HASH": PasswordHasher().hash(password),
           "JWT_SECRET": secrets.token_urlsafe(48), "JWT_EXPIRATION_MINUTES": "120",
           "MOBILIZA_SEGFORMER_CHECKPOINT": str(checkpoints[0]), "MOBILIZA_DINO_CHECKPOINT": str(checkpoints[1]),
           "MOBILIZA_DEVICE": "cpu", "MOBILIZA_CORS_ORIGINS": "http://127.0.0.1:4175",
           "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2"}
    with tempfile.TemporaryDirectory(prefix="permear-workspace-") as temp:
        dataset = Path(temp) / "dataset"
        target = dataset / "images/curb_ramp" / image.name
        target.parent.mkdir(parents=True)
        shutil.copyfile(image, target)
        with (ROOT / "annotations/transitability_annotations.csv").open(encoding="utf-8-sig",newline="") as f:
            rows = list(csv.DictReader(f))
        row = next(r for r in rows if r["filename"] == "curb_ramp/" + image.name)
        with (dataset / "transitability_annotations.csv").open("w",encoding="utf-8",newline="") as f:
            writer = csv.DictWriter(f,fieldnames=list(row));writer.writeheader();writer.writerow(row)
        with (evidence / "api.log").open("w",encoding="utf-8") as log:
            server = subprocess.Popen([os.sys.executable,"-m","uvicorn","scripts.validate_workspace:create_validation_app","--factory","--host","127.0.0.1","--port","8765"],cwd=ROOT,env=env,stdout=log,stderr=log)
            try:
                for _ in range(120):
                    if server.poll() is not None:raise RuntimeError("API local não iniciou; consulte api.log")
                    try:
                        with urlopen("http://127.0.0.1:8765/health",timeout=2) as response:
                            if response.status == 200:break
                    except Exception:time.sleep(1)
                else:raise TimeoutError("API local não ficou pronta")
                browser_env = {**os.environ,"WORKSPACE_EVIDENCE_DIR":str(evidence),"VITE_API_URL":"http://127.0.0.1:8765",
                               "WORKSPACE_TEST_USERNAME":env["AUTH_USERNAME"],"WORKSPACE_TEST_PASSWORD":password,
                               "WORKSPACE_TEST_IMAGE":str(image),"WORKSPACE_TEST_DATASET":str(dataset)}
                result = subprocess.run(["npm.cmd" if os.name=="nt" else "npm","run","test:e2e"],cwd=ROOT/"frontend",env=browser_env)
                if result.returncode:raise RuntimeError("Teste real do navegador falhou")
                exported = load_annotations(evidence/"exported_annotations.csv",load_schema(ROOT/"annotations/annotation-schema.yaml"))
                assert len(exported)==1
                direct = load_annotations(evidence/"direct-write.csv",load_schema(ROOT/"annotations/annotation-schema.yaml"))
                reviewed = load_annotations(evidence/"suggestion-reviewed.csv",load_schema(ROOT/"annotations/annotation-schema.yaml"))
                assert len(direct)==len(reviewed)==1
                assert "SegFormer common-dino-split" in next(iter(reviewed.values()))["comment"]
                assert next(iter(reviewed.values()))["circulation_path_origin"]=="manual"
                saved = next(iter(exported.values()))
                assert saved["obstruction"]=="full"
                assert len(saved["circulation_path"])==2
                assert hashlib.sha256(image.read_bytes()).hexdigest()==hashlib.sha256(target.read_bytes()).hexdigest()
                assert hashes=={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in checkpoints}
                (evidence/"validation.json").write_text(json.dumps({"real_browser_api_cpu":True,"supabase_http_test_double":True,"remote_supabase_validated":False,"export_loaded_by_python":True,
                    "annotation_rows":len(exported),"timestamps_simulated":True,"checkpoint_hashes":hashes},indent=2),encoding="utf-8")
                print("Workspace validado com API real, CPU e CSV aceito pelo carregador Python.")
            finally:
                server.terminate()
                try:server.wait(timeout=15)
                except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=="__main__":main()
