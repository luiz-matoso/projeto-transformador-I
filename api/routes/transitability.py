import base64
import logging
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from api.dependencies import get_components
from api.schemas.transitability import TransitabilityInput, TransitabilityOutput
from ml.mobility_profile import MobilityProfile
from ml.observation import evaluate_observation
from ml.pipeline import INACTIVE_FEATURES, apply_profile, observe_scene


router = APIRouter()
logger = logging.getLogger(__name__)
FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


def process_upload(upload, payload, settings, components):
    if upload.content_type not in FORMATS:
        raise HTTPException(415, "Formatos aceitos: JPEG, PNG, WebP")
    if upload.size is not None and upload.size > settings.max_image_bytes:
        raise HTTPException(413, "Imagem excede o limite de bytes")
    upload.file.seek(0, 2)
    if upload.file.tell() > settings.max_image_bytes:
        raise HTTPException(413, "Imagem excede o limite de bytes")
    upload.file.seek(0)
    try:
        with Image.open(upload.file) as source:
            if source.format != FORMATS[upload.content_type]:
                raise HTTPException(415, "Conteúdo da imagem não corresponde ao Content-Type")
            if source.width * source.height > settings.max_pixels or max(source.size) > settings.max_dimension:
                raise HTTPException(413, "Dimensões da imagem excedem o limite")
            if getattr(source, "n_frames", 1) != 1:
                raise HTTPException(422, "Imagens animadas não são suportadas")
            source.verify()
        upload.file.seek(0)
        with Image.open(upload.file) as source:
            image = source.convert("RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise HTTPException(413, "Imagem excede o limite de pixels") from error
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise HTTPException(422, "Arquivo não é uma imagem válida") from error

    now = datetime.now(timezone.utc)
    observation = payload.observation.model_dump()
    period = timedelta(hours=payload.validity_hours)
    temporal = evaluate_observation(observation, validity_period=period, evaluated_at=now)
    if temporal["is_valid"]:
        scene = observe_scene(image, observation=observation, components=components)
        buffer = BytesIO()
        Image.fromarray(scene.pop("mask") * 255).save(buffer, format="PNG")
        mask = {"encoding": "base64_png", "media_type": "image/png", "width": image.width,
                "height": image.height, "data": base64.b64encode(buffer.getbuffer()).decode("ascii")}
    else:
        scene = {"features": {}, "predictions": {}, "not_modeled": components[-1],
                 "inactive_features": list(INACTIVE_FEATURES), "observation": observation}
        mask = None
    image.close()
    assessments = []
    for index, profile in enumerate(payload.profiles):
        result = apply_profile(scene, MobilityProfile(**profile.model_dump()), validity_period=period, evaluated_at=now)
        assessments.append({"profile_index": index, **{key: result[key] for key in
                            ("profile", "classification", "severity", "reasons", "requires_review", "unassessed_features")}})
    return {"mask": mask, "features": scene["features"], "predictions": scene["predictions"],
            "observation": result["observation"], "not_modeled": scene["not_modeled"],
            "inactive_features": scene["inactive_features"], "assessments": assessments}


@router.post("/transitability", response_model=TransitabilityOutput,
             responses={413: {"description": "Limite de tamanho ou dimensões"}, 415: {"description": "Formato não suportado"},
                        422: {"description": "Entrada inválida"}, 503: {"description": "Modelos indisponíveis ou capacidade ocupada"}})
async def transitability(request: Request, image: Annotated[UploadFile, File()],
                         metadata: Annotated[str, Form(description="JSON conforme TransitabilityInput")],
                         components=Depends(get_components)):
    try:
        try:
            payload = TransitabilityInput.model_validate_json(metadata)
        except ValidationError as error:
            raise HTTPException(422, error.errors(include_url=False, include_context=False, include_input=False)) from error
        return await run_in_threadpool(process_upload, image, payload, request.app.state.settings, components)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Falha na inferência de transitabilidade")
        raise HTTPException(503, "Falha na inferência; tente novamente") from error
    finally:
        await image.close()
