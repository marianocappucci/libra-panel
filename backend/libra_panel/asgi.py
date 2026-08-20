"""Punto de entrada de uvicorn: `uvicorn libra_panel.asgi:app`."""
from .app import create_app

app = create_app()
