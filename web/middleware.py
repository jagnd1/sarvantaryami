import logging
import traceback
from starlette.types import ASGIApp, Scope, Receive, Send
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
import uuid

logger = logging.getLogger(__name__)

class BusinessLogicException(Exception):
    def __init__(self, detail: str):
        self.detail = detail

class ReqIDExceptionMiddleware:
    """ Middleware for request ID logging and exception handling """
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Generate request ID
        req_id = str(uuid.uuid4())
        req = Request(scope)
        # Store in scope state slightly differently than starlette default to match fm-iss if needed
        # but usually request.state is used. fm-iss used scope['state'] manually.
        # We will follow fm-iss pattern of injecting into scope['state'].
        if 'state' not in scope:
            scope['state'] = {}
        scope['state']['request_id'] = req_id

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                headers[b"x-request-id"] = req_id.encode()
                message["headers"] = list(headers.items())
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            logger.error(f"[{req_id}] Error: {str(e)}")
            traceback.print_exc()
            
            status_code = 500
            detail = "Internal Server Error"
            
            if isinstance(e, BusinessLogicException):
                status_code = 400
                detail = e.detail
            elif isinstance(e, StarletteHTTPException):
                status_code = e.status_code
                detail = e.detail
            
            response = JSONResponse(
                status_code=status_code, 
                content={"status": "error", "detail": detail}
            )
            await response(scope, receive, send)

async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"status": "error", "detail": exc.detail})

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"status": "error", "detail": str(exc.errors())})
