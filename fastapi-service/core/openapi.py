from fastapi import FastAPI


def custom_openapi(app: FastAPI):
    """Generate custom OpenAPI schema with RFC 7807 Problem Details."""
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    servers = [{"url": app.root_path}] if app.root_path else None

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        servers=servers,
    )

    paths = openapi_schema.get("paths", {})
    for path in paths.values():
        for method in path.values():
            responses = method.get("responses", {})
            if "422" in responses:
                content = responses["422"].get("content", {})
                json_schema = content.get("application/json", {}).get("schema", {})
                ref = json_schema.get("$ref", "")
                if "HTTPValidationError" in ref:
                    del responses["422"]
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)

    app.openapi_schema = openapi_schema
    return app.openapi_schema
