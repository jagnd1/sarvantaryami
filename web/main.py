from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from web.routers.v1.chatbot import router as chatbot_router
from web.middleware import ReqIDExceptionMiddleware, http_exception_handler, validation_exception_handler

app = FastAPI(title="Sarvantaryami Agent")

# Add Middleware
app.add_middleware(ReqIDExceptionMiddleware)

# Exception Handlers
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# Include Routers
app.include_router(chatbot_router, prefix="/api/v1/cb", tags=["chatbot"])
