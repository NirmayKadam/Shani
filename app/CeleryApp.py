# app/CeleryApp.py — Root-level compatibility shim
#
# The real Celery instance lives at app/Core/CeleryApp.py.
# This file re-exports it so that all existing task files
# can continue to import via: from app.CeleryApp import CeleryApp

from app.Core.CeleryApp import CeleryApp, app  # noqa: F401
