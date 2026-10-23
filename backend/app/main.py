"""Arthvest FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.macro import router as macro_router

app = FastAPI(
    title="Arthvest API",
    description="Macro Intelligence API for the Arthvest platform.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(macro_router)


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    """Expose a small API welcome response."""
    return {
        "name": "Arthvest API",
        "status": "running",
        "docs": "/docs",
    }
