"""Run the controlled order service from environment-backed settings."""

import uvicorn

from bugcapsule.demo.app import create_demo_app
from bugcapsule.demo.config import DemoSettings


def main() -> None:
    """Start the demo service on its configured interface."""
    settings = DemoSettings()
    uvicorn.run(
        create_demo_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
