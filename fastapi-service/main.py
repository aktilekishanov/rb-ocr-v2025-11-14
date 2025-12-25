"""FastAPI application entry point."""

from dotenv import load_dotenv

load_dotenv()

import logging
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic_core import ValidationError as PydanticCoreValidationError

from core.lifespan import lifespan
from core.openapi import custom_openapi
from core.middleware import trace_id_middleware
from core.error_handlers import (
    handle_validation_error,
    handle_pydantic_error,
    handle_http_error,
    handle_app_error,
    handle_unknown_error,
)
from api.routes import health, verify, kafka
from pipeline.core.logging_config import configure_structured_logging
from pipeline.core.exceptions import BaseError

# Configure logging
configure_structured_logging(level="INFO", json_format=True)
logger = logging.getLogger(__name__)

# Suppress known warnings
import urllib3

# Suppress urllib3 SSL verification warnings (S3 uses self-signed certs in dev)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Suppress pypdf warnings about malformed PDF metadata (not our issue)
logging.getLogger("pypdf").setLevel(logging.ERROR)

# Initialize FastAPI app
app = FastAPI(
    title="RB-OCR Document Verification API",
    version="1.0.0",
    description="Validates loan deferment documents",
    docs_url="/docs",
    redoc_url="/redoc",
    root_path="/rb-ocr/api",
    lifespan=lifespan,
)

# Custom OpenAPI
app.openapi = lambda: custom_openapi(app)

# 1. Register Middleware
app.middleware("http")(trace_id_middleware)

# 2. Register Exception Handlers
app.add_exception_handler(RequestValidationError, handle_validation_error)
app.add_exception_handler(PydanticCoreValidationError, handle_pydantic_error)
app.add_exception_handler(StarletteHTTPException, handle_http_error)
app.add_exception_handler(BaseError, handle_app_error)
app.add_exception_handler(Exception, handle_unknown_error)

# Routes
app.include_router(health.router)
app.include_router(verify.router)
app.include_router(kafka.router)
