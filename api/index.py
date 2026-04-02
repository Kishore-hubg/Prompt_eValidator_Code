"""Vercel serverless entry — ASGI app must live under /api."""

from app.main import app

__all__ = ["app"]
