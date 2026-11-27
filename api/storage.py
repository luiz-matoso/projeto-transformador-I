"""Private Supabase REST/Storage access; one pooled HTTP client per process."""
import asyncio
import base64
import hashlib
import json
from urllib.parse import quote
import httpx
from fastapi import HTTPException
from api.config import environment

class WorkspaceStorage:
    def __init__(self, url, secret, *, transport=None):
        self.url = url.rstrip("/")
        headers = {"apikey": secret}
        if not secret.startswith("sb_secret_"):
            headers["Authorization"] = "Bearer " + secret
        self.client = httpx.AsyncClient(base_url=self.url, headers=headers, timeout=30, limits=httpx.Limits(max_connections=4), transport=transport)
        self.lock = asyncio.Lock()
        self.bucket = "workspace-analyses"

    @classmethod
    def from_env(cls):
        env = environment()
        url, secret = env("SUPABASE_URL", default=""), env("SUPABASE_SECRET_KEY", default="")
        if not url and not secret:
            return None
        if not url or not secret or not url.startswith("https://"):
            raise ValueError("Configuração de persistência inválida")
        return cls(url, secret)

    async def close(self):
        await self.client.aclose()

    async def call(self, method, path, **kwargs):
        try:
            response = await self.client.request(method, path, **kwargs)
            if not response.is_success:
                if response.status_code == 409:
                    raise HTTPException(409, "Registro já existe ou foi alterado")
                raise HTTPException(503, "Não foi possível acessar os dados; tente novamente")
            return response.json() if response.content else None
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, "Não foi possível acessar os dados; tente novamente") from None

    async def profiles(self, owner):
        return await self.call("GET", "/rest/v1/profiles", params={"owner": "eq." + owner,
            "select": "id,name,requirements,functional,created_at,updated_at", "order": "created_at.asc"})

    async def save_profile(self, owner, profile, update=False):
        body = profile.model_dump(mode="json", exclude_none=True)
        if update:
            if profile.functional is None:
                previous = await self.call("GET", "/rest/v1/profiles", params={"id": "eq." + body["id"], "owner": "eq." + owner})
                if previous and previous[0].get("functional") is not None:
                    if previous[0]["requirements"] != body["requirements"]:
                        raise HTTPException(409, "Atualize as respostas funcionais para alterar os requisitos")
                    body["functional"] = previous[0]["functional"]
            rows = await self.call("PATCH", "/rest/v1/profiles", params={"id": "eq." + body.pop("id"), "owner": "eq." + owner},
                json=body, headers={"Prefer": "return=representation"})
        else:
            rows = await self.call("POST", "/rest/v1/profiles", json={**body, "owner": owner},
                headers={"Prefer": "resolution=ignore-duplicates,return=representation"})
            if not rows:
                existing = [p for p in await self.profiles(owner) if p["id"] == body["id"]]
                if not existing or any(existing[0].get(k) != body.get(k) for k in ("name", "requirements", "functional")):
                    raise HTTPException(409, "Identificador já utilizado por outro perfil")
                rows = existing
        if not rows:
            raise HTTPException(404, "Perfil não encontrado")
        return rows[0]

    async def delete_profile(self, owner, identifier):
        await self.call("DELETE", "/rest/v1/profiles", params={"id": "eq." + identifier, "owner": "eq." + owner})

    async def get_analysis(self, owner, identifier):
        rows = await self.call("GET", "/rest/v1/analyses", params={"id": "eq." + identifier, "owner": "eq." + owner})
        if not rows:
            raise HTTPException(404, "Análise não encontrada")
        return rows[0]

    async def list_analyses(self, owner, offset=0):
        return await self.call("GET", "/rest/v1/analyses", params={"owner": "eq." + owner, "status": "in.(complete,deleting)",
            "select": "id,created_at,profiles,status", "order": "created_at.desc,id.desc", "limit": "20", "offset": str(offset)})

    async def save_analysis(self, owner, payload, original, content_type, versions):
        body = payload.model_dump(mode="json", exclude_none=True)
        for index, profile in enumerate(payload.profiles):
            if profile.functional != payload.result.assessments[index].functional:
                raise HTTPException(422, "Respostas funcionais incompatíveis com o resultado")
            if profile.requirements != payload.result.assessments[index].profile:
                raise HTTPException(422, "Perfil incompatível com o resultado")
        mask = base64.b64decode(payload.result.mask.data, validate=True) if payload.result.mask else None
        result = body["result"]
        result["mask"] = None
        identifier = str(payload.id)
        fingerprint = hashlib.sha256(original + (mask or b"") + json.dumps(body, sort_keys=True).encode()).hexdigest()
        prefix = hashlib.sha256(owner.encode()).hexdigest()[:24] + "/" + identifier
        paths = {"image_path": prefix + "/original", "mask_path": prefix + "/mask.png" if mask else None}
        async with self.lock:
            rows = await self.call("POST", "/rest/v1/analyses", json={"id": identifier, "owner": owner,
                "profiles": body["profiles"], "result": result, "model_versions": versions, "fingerprint": fingerprint,
                "status": "pending", **paths}, headers={"Prefer": "resolution=ignore-duplicates,return=representation"})
            record = rows[0] if rows else await self.get_analysis(owner, identifier)
            if record["fingerprint"] != fingerprint or record["status"] == "deleting":
                raise HTTPException(409, "Identificador já utilizado; não foi criada outra análise")
            if record["status"] != "complete":
                for path, data, mime in [(paths["image_path"], original, content_type), (paths["mask_path"], mask, "image/png")]:
                    if path:
                        await self.call("POST", "/storage/v1/object/" + self.bucket + "/" + path,
                            content=data, headers={"Content-Type": mime, "x-upsert": "true"})
                await self.call("PATCH", "/rest/v1/analyses", params={"id": "eq." + identifier, "owner": "eq." + owner}, json={"status": "complete"})
        return {"id": identifier, "status": "complete"}

    async def analysis_detail(self, owner, identifier):
        record = await self.get_analysis(owner, identifier)
        if record["status"] != "complete":
            raise HTTPException(409, "Análise ainda não disponível")
        for kind in ("image", "mask"):
            path = record.get(kind + "_path")
            record[kind + "_url"] = None
            if path:
                response = await self.call("POST", "/storage/v1/object/sign/" + self.bucket + "/" + quote(path, safe="/"), json={"expiresIn": 300})
                signed = response.get("signedURL") or response.get("signedUrl")
                if not isinstance(signed, str) or not signed:
                    raise HTTPException(503, "Não foi possível abrir o arquivo; tente novamente")
                if signed.startswith("/object/"):
                    signed = self.url + "/storage/v1" + signed
                elif signed.startswith("/"):
                    signed = self.url + signed
                record[kind + "_url"] = signed
        return {key: record.get(key) for key in ("id", "created_at", "profiles", "result", "model_versions", "image_url", "mask_url")}

    async def delete_analysis(self, owner, identifier):
        async with self.lock:
            try:
                record = await self.get_analysis(owner, identifier)
            except HTTPException as error:
                if error.status_code == 404:
                    return
                raise
            await self.call("PATCH", "/rest/v1/analyses", params={"id": "eq." + identifier, "owner": "eq." + owner}, json={"status": "deleting"})
            paths = [record[key] for key in ("image_path", "mask_path") if record.get(key)]
            if paths:
                await self.call("DELETE", "/storage/v1/object/" + self.bucket, json={"prefixes": paths})
            await self.call("DELETE", "/rest/v1/analyses", params={"id": "eq." + identifier, "owner": "eq." + owner})
