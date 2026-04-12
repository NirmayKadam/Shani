# app/Infrastructure/CeleryApp.py  —  Re-export only
#
# The real Celery instance lives in app/Core/CeleryApp.py.
# This file exists so that `from app.Infrastructure.CeleryApp import CeleryApp`
# still works for any code that was written against the old path.

from app.Core.CeleryApp import CeleryApp  # noqa: F401

