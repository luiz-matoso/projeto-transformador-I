from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer

from api.auth import unauthorized


def get_components(request: Request):
    components = request.app.state.components
    if components is None:
        raise HTTPException(503, "Modelos indisponíveis")
    return components


def get_current_user(request: Request, credentials=Depends(HTTPBearer(auto_error=False))):
    user = getattr(request.state, "auth_user", None)
    if user is None:
        raise unauthorized()
    return user
