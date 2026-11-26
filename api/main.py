import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from api.config import Settings
from api.routes.transitability import router
from api.schemas.transitability import HealthOutput, TransitabilityInput
from ml.pipeline import load_components


logger = logging.getLogger(__name__)


class RequestLimits:
    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/transitability":
            return await self.app(scope, receive, send)
        application = scope["app"]
        gate = application.state.gate
        if gate.locked():
            return await JSONResponse({"detail": "Capacidade ocupada; tente novamente"}, status_code=503,
                                      headers={"Retry-After": "1"})(scope, receive, send)
        size = 0
        async def limited_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > self.max_bytes:
                    raise HTTPException(413, "Corpo da requisição excede o limite")
            return message
        async with gate:
            await self.app(scope, limited_receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.gate = asyncio.Semaphore(settings.max_concurrency)
        app.state.components = None
        try:
            app.state.components = await run_in_threadpool(load_components, settings.segformer_checkpoint, settings.dino_checkpoint, settings.device)
            logger.info("Modelos carregados; device=%s", app.state.components[4])
        except Exception:
            logger.exception("Modelos indisponíveis durante inicialização")
        try:
            yield
        finally:
            app.state.components = None
            load_components.cache_clear()

    app = FastAPI(title="Mobiliza Transitability API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.components = None
    app.add_middleware(RequestLimits, max_bytes=settings.max_image_bytes + 128 * 1024)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"], allow_credentials=False)
    app.include_router(router)

    @app.get("/health", response_model=HealthOutput, responses={503: {"model": HealthOutput}})
    async def health(request: Request):
        components = request.app.state.components
        payload = {"status": "ready" if components is not None else "unavailable",
                   "models_loaded": components is not None, "device": str(components[4]) if components is not None else None}
        if components is None:
            return JSONResponse(payload, status_code=503)
        return payload

    original_openapi = app.openapi
    def openapi():
        if app.openapi_schema is None:
            schema = original_openapi()
            metadata = TransitabilityInput.model_json_schema(ref_template="#/components/schemas/{model}")
            schema["components"]["schemas"].update(metadata.pop("$defs", {}))
            schema["components"]["schemas"]["TransitabilityInput"] = metadata
            app.openapi_schema = schema
        return app.openapi_schema
    app.openapi = openapi
    return app


app = create_app()
