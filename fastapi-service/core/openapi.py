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

    # Remove the default validation error schemas and references
    # 1. Iterate over all paths and methods to remove references to HTTPValidationError
    paths = openapi_schema.get("paths", {})
    for path in paths.values():
        for method in path.values():
            responses = method.get("responses", {})
            # If 422 exists and references HTTPValidationError, remove it
            # (Note: Our custom ProblemDetail responses override this anyway,
            # but FastAPI might have merged them or kept the reference)
            if "422" in responses:
                content = responses["422"].get("content", {})
                json_schema = content.get("application/json", {}).get("schema", {})
                ref = json_schema.get("$ref", "")
                if "HTTPValidationError" in ref:
                    del responses["422"]

    # 2. Now safe to remove the schema definitions
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)

    app.openapi_schema = openapi_schema
    return app.openapi_schema
