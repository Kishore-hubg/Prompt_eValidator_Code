"""Vercel serverless entry — ASGI app exposed as `handler` for @vercel/python."""

import sys
import os

# Ensure project root is on sys.path so that top-level packages
# (teams_bot/, app/) are importable when running inside Vercel Functions.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.main import app

# Vercel Python runtime discovers this file as a serverless function
# via the `handler` variable (ASGI-compatible FastAPI app).
handler = app
