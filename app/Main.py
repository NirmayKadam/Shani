# app/Main.py — Root-level compatibility shim
#
# The real FastAPI app lives at app/Core/Main.py.
# This file re-exports it so that uvicorn can reference: app.Main:App

from app.Core.Main import App  # noqa: F401
