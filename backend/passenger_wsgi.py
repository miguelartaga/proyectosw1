"""WSGI entrypoint for FastAPI when running under cPanel's Passenger.

Passenger expects a WSGI callable named `application`. We wrap the FastAPI
ASGI app so it can respond through the WSGI interface.
"""
import os
import sys
from pathlib import Path

from a2wsgi import ASGIMiddleware
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env", override=False)

from app.main import app as fastapi_app  # noqa: E402  (import after sys.path tweak)

application = ASGIMiddleware(fastapi_app)