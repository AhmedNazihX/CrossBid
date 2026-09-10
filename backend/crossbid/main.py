"""App factory.

Deliberately thin at this stage. CORS, rate limiting, routers, and the
checkpointer/store startup hooks arrive with the stories that need them
(S0.2.2, S0.3.2, S2.3.3); see docs/project-plan.md.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel


class Health(BaseModel):
    status: str
    service: str


def create_app() -> FastAPI:
    app = FastAPI(
        title="Crossbid API",
        version="0.1.0",
        description="Cross-border EU tender go/no-go qualification agent.",
    )

    @app.get("/health", response_model=Health, tags=["meta"])
    async def health() -> Health:
        """Liveness probe. Used by Compose and by the smoke test."""
        return Health(status="ok", service="crossbid-api")

    return app


app = create_app()
