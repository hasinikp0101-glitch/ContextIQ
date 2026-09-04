"""Entrypoint re-exporting the ContextForge FastAPI application."""

from app.main import app, home

__all__ = ["app", "home"]