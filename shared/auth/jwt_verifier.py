"""
File Overview: Verification of Supabase access tokens (JWT).

All Functions/Classes:
- AuthError: Raised when a token is missing, malformed, expired or wrongly signed.
- SupabaseJwtVerifier: Verifies signature, expiry and audience; returns the claims. Data: token -> claims.
- get_jwt_verifier: Process-wide verifier built from settings.

Supabase projects sign access tokens either with asymmetric keys (ES256/RS256, public keys at
{SUPABASE_URL}/auth/v1/.well-known/jwks.json) or, for legacy projects, with an HS256 shared
secret (SUPABASE_JWT_SECRET). Both are supported; the token header's `alg` selects the path.

Endpoints/APIs: Supabase JWKS endpoint (fetched once, then cached).

Database Tables: None
"""
import logging
from functools import lru_cache
from typing import Optional

import jwt
from jwt import PyJWKClient

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

_ASYMMETRIC_ALGORITHMS = {"ES256", "RS256"}
_AUDIENCE = "authenticated"


class AuthError(Exception):
    """The token could not be verified; the message is safe to return to the client."""


class SupabaseJwtVerifier:
    def __init__(self, supabase_url: str = "", jwt_secret: str = "", audience: str = _AUDIENCE):
        self._secret = jwt_secret
        self._audience = audience
        self._jwks: Optional[PyJWKClient] = None
        if supabase_url:
            jwks_url = supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
            self._jwks = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600, timeout=5)

    @property
    def configured(self) -> bool:
        return bool(self._secret or self._jwks)

    def verify(self, token: str) -> dict:
        """Return the verified claims (including `sub`, the user id). Blocking on first JWKS fetch."""
        if not token:
            raise AuthError("Missing bearer token")
        try:
            alg = jwt.get_unverified_header(token).get("alg")
        except jwt.PyJWTError:
            raise AuthError("Malformed token")

        if alg == "HS256":
            if not self._secret:
                raise AuthError("HS256 tokens are not accepted by this server")
            key = self._secret
        elif alg in _ASYMMETRIC_ALGORITHMS and self._jwks is not None:
            try:
                key = self._jwks.get_signing_key_from_jwt(token).key
            except jwt.PyJWKClientError as exc:
                logger.warning("JWKS signing key lookup failed: %s", exc)
                raise AuthError("Unknown signing key")
        else:
            raise AuthError("Unsupported token algorithm")

        try:
            return jwt.decode(
                token,
                key,
                algorithms=[alg],
                audience=self._audience,
                options={"require": ["exp", "sub"]},
            )
        except jwt.ExpiredSignatureError:
            raise AuthError("Token expired")
        except jwt.PyJWTError as exc:
            raise AuthError(f"Invalid token: {exc}")


@lru_cache(maxsize=1)
def get_jwt_verifier() -> SupabaseJwtVerifier:
    settings = get_settings()
    return SupabaseJwtVerifier(settings.SupabaseUrl, settings.SupabaseJwtSecret)
