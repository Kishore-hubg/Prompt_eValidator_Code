"""Vercel serverless entry — ASGI app exposed as `handler` for @vercel/python."""

from app.main import app

# Vercel Python runtime discovers this file as a serverless function
# via the `handler` variable (ASGI-compatible FastAPI app).
handler = app
