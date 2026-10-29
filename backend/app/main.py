"""Arthvest FastAPI application entrypoint."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.macro import router as macro_router
from app.api.routes.market import market_data_router, router as market_router
from app.api.routes.user_data import router as watchlist_router

def configured_cors_origins() -> list[str]:
    """Read comma-separated frontend origins from the environment."""
    default = "http://localhost:3000,http://127.0.0.1:3000"
    configured = os.getenv("CORS_ORIGINS", default)
    return [
        origin.strip().rstrip("/")
        for origin in configured.split(",")
        if origin.strip()
    ]


app = FastAPI(
    title="Arthvest API",
    description="Macro Intelligence API for the Arthvest platform.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(macro_router)
app.include_router(market_data_router)
app.include_router(market_router)
app.include_router(watchlist_router)


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    """Expose a small API welcome response."""
    return {
        "name": "Arthvest API",
        "status": "running",
        "docs": "/docs",
    }
