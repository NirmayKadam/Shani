# app/Config.py — Root-level compatibility shim
#
# The real Config lives at app/Core/Config.py.
# This file re-exports it so that Infrastructure modules
# can continue to import via: from app.Config import GetSettings

from app.Core.Config import GetSettings  # noqa: F401
