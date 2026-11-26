from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from api.schemas.auth import LoginInput, TokenOutput


router = APIRouter()


@router.post("/auth/login", response_model=TokenOutput,
             responses={401: {"description": "Credenciais inválidas"},
                        429: {"description": "Limite de tentativas"}})
async def login(payload: LoginInput, request: Request, response: Response):
    result = await run_in_threadpool(request.app.state.auth.login,
                                    payload.username, payload.password.get_secret_value())
    response.headers["Cache-Control"] = "no-store"
    return result
