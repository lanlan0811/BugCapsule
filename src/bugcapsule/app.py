"""FastAPI application factory for the local BugCapsule service."""

from fastapi import FastAPI

from bugcapsule import __version__


def create_app() -> FastAPI:
    """Build a new local API application instance."""
    application = FastAPI(
        title="BugCapsule",
        description="Evidence-first AI debugging",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    @application.get("/healthz", tags=["system"])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return application


app = create_app()
