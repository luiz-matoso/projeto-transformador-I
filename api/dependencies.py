from fastapi import HTTPException, Request


def get_components(request: Request):
    components = request.app.state.components
    if components is None:
        raise HTTPException(503, "Modelos indisponíveis")
    return components
