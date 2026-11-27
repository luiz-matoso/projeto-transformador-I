import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.datastructures import Headers

from api.config import Settings, AuthSettings
from api.auth import Authentication, LOGIN_LIMIT, INFERENCE_LIMIT, RATE_WINDOW_SECONDS
from api.routes.auth import router as auth_router
from api.routes.transitability import router
from api.schemas.transitability import HealthOutput, TransitabilityInput
from ml.pipeline import load_components


logger = logging.getLogger(__name__)


class RequestLimits:
    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in ("/transitability", "/auth/login"):
            return await self.app(scope, receive, send)
        application = scope["app"]
        auth = application.state.auth
        if auth is None:
            return await JSONResponse({"detail": "Autenticação indisponível"}, status_code=503)(scope, receive, send)
        login = scope["path"] == "/auth/login"
        if login:
            key, limit = "login", LOGIN_LIMIT
        else:
            try:
                user = auth.authenticate(Headers(scope=scope).get("authorization"))
            except HTTPException as error:
                return await JSONResponse({"detail": error.detail}, status_code=error.status_code,
                                          headers=error.headers)(scope, receive, send)
            scope.setdefault("state", {})["auth_user"] = user
            key, limit = "inference:" + user, INFERENCE_LIMIT
        if not auth.limiter.allow(key, limit):
            return await JSONResponse({"detail": "Limite de requisições excedido"}, status_code=429,
                                      headers={"Retry-After": str(RATE_WINDOW_SECONDS)})(scope, receive, send)
        gate = application.state.login_gate if login else application.state.gate
        if gate.locked():
            status = 429 if login else 503
            return await JSONResponse({"detail": "Capacidade ocupada; tente novamente"}, status_code=status,
                                      headers={"Retry-After": "1"})(scope, receive, send)
        size = 0
        max_bytes = 4096 if login else self.max_bytes
        async def limited_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > max_bytes:
                    raise HTTPException(413, "Corpo da requisição excede o limite")
            return message
        async with gate:
            await self.app(scope, limited_receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.auth = Authentication(AuthSettings.from_env())
        app.state.login_gate = asyncio.Semaphore(1)
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
            app.state.auth = None
            load_components.cache_clear()

    app = FastAPI(title="Mobiliza Transitability API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.auth = None
    app.state.components = None
    app.add_middleware(RequestLimits, max_bytes=settings.max_image_bytes + 128 * 1024)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"], allow_credentials=False)
    app.include_router(router)
    app.include_router(auth_router)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        if request.url.path == "/auth/login":
            return JSONResponse({"detail": "Credenciais ou token inválidos"}, status_code=401,
                                headers={"WWW-Authenticate": "Bearer"})
        return await request_validation_exception_handler(request, error)

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
