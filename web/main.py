from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from infrastructure.config import settings
from web.routers.v1.agent import router as agent_router
from web.middleware import ReqIDExceptionMiddleware, http_exception_handler, validation_exception_handler

app = FastAPI(title=settings.API_TITLE, version=settings.API_VERSION)

# Add Middleware
app.add_middleware(ReqIDExceptionMiddleware)

# Exception Handlers
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# Include Routers
app.include_router(agent_router, prefix="/api/v1/agent", tags=["agent"])
