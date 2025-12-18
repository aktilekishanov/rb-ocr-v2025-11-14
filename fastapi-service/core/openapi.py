from fastapi import FastAPI


def custom_openapi(app: FastAPI):
    """Custom OpenAPI schema generator to remove default validation errors."""
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    # Ensure Swagger UI uses the correct root path
    servers = [{"url": app.root_path}] if app.root_path else None

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        servers=servers,
    )

    # Remove the default validation error schemas if they exist
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)

    app.openapi_schema = openapi_schema
    return app.openapi_schema
