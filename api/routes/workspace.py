import base64
import hashlib
from functools import lru_cache
from io import BytesIO
from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from PIL import Image
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from api.dependencies import get_current_user
from api.schemas.workspace import AnalysisWrite, ProfileWrite, ProfileRecord, AnalysisSaved, AnalysisSummary, AnalysisDetail

router = APIRouter(dependencies=[Depends(get_current_user)])

def storage(request: Request):
    store = getattr(request.app.state, "storage", None)
    if store is None:
        raise HTTPException(503, "Persistência indisponível")
    return store

@lru_cache(maxsize=2)
def checkpoint_version(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return {"checkpoint": path.name, "sha256": digest.hexdigest()}

@router.get("/profiles", response_model=list[ProfileRecord])
async def list_profiles(request: Request, user=Depends(get_current_user)):
    return await storage(request).profiles(user)

@router.post("/profiles", response_model=ProfileRecord)
async def create_profile(payload: ProfileWrite, request: Request, user=Depends(get_current_user)):
    return await storage(request).save_profile(user, payload)

@router.put("/profiles/{identifier}", response_model=ProfileRecord)
async def update_profile(identifier: UUID, payload: ProfileWrite, request: Request, user=Depends(get_current_user)):
    if identifier != payload.id:
        raise HTTPException(422, "Identificadores incompatíveis")
    return await storage(request).save_profile(user, payload, update=True)

@router.delete("/profiles/{identifier}", status_code=204)
async def delete_profile(identifier: UUID, request: Request, user=Depends(get_current_user)):
    await storage(request).delete_profile(user, str(identifier))
    return Response(status_code=204)

@router.get("/analyses", response_model=list[AnalysisSummary])
async def list_analyses(request: Request, offset: int = 0, user=Depends(get_current_user)):
    if offset < 0 or offset > 100000:
        raise HTTPException(422, "Página inválida")
    return await storage(request).list_analyses(user, offset)

@router.get("/analyses/{identifier}", response_model=AnalysisDetail)
async def get_analysis(identifier: UUID, request: Request, user=Depends(get_current_user)):
    return await storage(request).analysis_detail(user, str(identifier))

def validate_images(original, content_type, payload, settings):
    from api.routes.transitability import FORMATS
    try:
        with Image.open(BytesIO(original)) as source:
            if source.format != FORMATS.get(content_type):
                raise ValueError()
            if source.width * source.height > settings.max_pixels or max(source.size) > settings.max_dimension or getattr(source, "n_frames", 1) != 1:
                raise ValueError()
            size = source.size
            source.verify()
        if payload.result.mask:
            mask = base64.b64decode(payload.result.mask.data, validate=True)
            with Image.open(BytesIO(mask)) as source:
                if source.format != "PNG" or source.size != size or source.size != (payload.result.mask.width, payload.result.mask.height):
                    raise ValueError()
                source.verify()
    except Exception:
        raise HTTPException(422, "Imagem ou máscara inválida") from None

@router.post("/analyses", response_model=AnalysisSaved)
async def save_analysis(request: Request, image: Annotated[UploadFile, File()], metadata: Annotated[str, Form()], user=Depends(get_current_user)):
    try:
        store = storage(request)
        if len(metadata.encode()) > 2 * 1024 * 1024:
            raise HTTPException(413, "Resultado excede o limite")
        try:
            payload = AnalysisWrite.model_validate_json(metadata)
        except ValidationError:
            raise HTTPException(422, "Dados da análise inválidos") from None
        original = await image.read(request.app.state.settings.max_image_bytes + 1)
        if len(original) > request.app.state.settings.max_image_bytes:
            raise HTTPException(413, "Imagem excede o limite")
        await run_in_threadpool(validate_images, original, image.content_type, payload, request.app.state.settings)
        settings = request.app.state.settings
        versions = {"segformer": await run_in_threadpool(checkpoint_version, settings.segformer_checkpoint),
                    "dinov2": await run_in_threadpool(checkpoint_version, settings.dino_checkpoint)}
        return await store.save_analysis(user, payload, original, image.content_type, versions)
    finally:
        await image.close()

@router.delete("/analyses/{identifier}", status_code=204)
async def delete_analysis(identifier: UUID, request: Request, user=Depends(get_current_user)):
    await storage(request).delete_analysis(user, str(identifier))
    return Response(status_code=204)
