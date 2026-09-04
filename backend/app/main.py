"""Main FastAPI application for ContextForge."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router

# Load environment variables from backend/.env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

app = FastAPI(
    title="ContextForge API",
    description="Developer context optimization and debugging pipeline.",
    version="0.1.0",
)

# Enable CORS for local React/Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root status route
@app.get("/")
def home() -> dict[str, str]:
    """Root endpoint verifying backend is running."""
    return {"message": "ContextForge backend is running!"}


# Mount the API router
app.include_router(api_router)
