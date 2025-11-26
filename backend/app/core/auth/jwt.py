"""JWT verification using Clerk JWKS and OIDC standards.

This module provides:
- JWT parsing and header inspection
- JWKS key lookup by kid
- JWT signature verification using python-jose
- Standard claims validation (iss, aud, exp, alg)
- Automatic JWKS refresh on signature mismatch
"""

import logging
from typing import TypedDict

from jose import jwt
from jose.exceptions import JWSSignatureError, JWTClaimsError, JWTError

from app.core.auth.jwks import fetch_jwks, invalidate_jwks_cache
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


class DecodedToken(TypedDict):
    """Decoded JWT token payload.

    Attributes:
        sub: Clerk user ID (subject claim)
        email: User email address
        name: User display name
        iss: Token issuer
        aud: Intended audience
        exp: Token expiration time (Unix timestamp)
    """

    sub: str
    email: str | None
    name: str | None
    iss: str
    aud: str
    exp: int


async def verify_clerk_jwt(token: str) -> DecodedToken:
    """Verify Clerk JWT token with JWKS signature validation.

    Steps:
    1. Parse JWT header to extract kid (key ID)
    2. Fetch cached JWKS and find matching key
    3. Verify signature using the public key
    4. Validate standard claims (iss, aud, exp, alg)
    5. Return decoded payload as DecodedToken

    On signature verification failure, automatically refreshes JWKS cache
    and retries once (single retry).

    Args:
        token: Bearer token (JWT string)

    Returns:
        DecodedToken with validated claims

    Raises:
        AppError: If token is invalid, expired, or signature verification fails (401)
    """
    settings = get_settings()

    if not settings.CLERK_JWKS_URL or not settings.CLERK_ISSUER:
        logger.error("Clerk JWKS_URL or ISSUER not configured")
        raise AppError(
            code=ErrorCode.UNAVAILABLE,
            http_status=503,
            message="Authentication provider not configured",
        )

    # Attempt verification with single retry on signature failure
    retry_count = 0
    max_retries = 1

    while retry_count <= max_retries:
        try:
            # Parse header without verification to get kid
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")

            if not kid:
                logger.warning("JWT missing kid in header")
                raise AppError(
                    code=ErrorCode.AUTH_INVALID,
                    http_status=401,
                    message="Invalid authentication token",
                )

            # Fetch JWKS
            jwks_data = await fetch_jwks()

            # Find matching key
            matching_key = None
            for key in jwks_data["keys"]:
                if key.get("kid") == kid:
                    matching_key = key
                    break

            if not matching_key:
                logger.warning(f"No matching key found for kid: {kid}")
                if retry_count < max_retries:
                    logger.info("JWKS refresh: retrying due to missing key")
                    invalidate_jwks_cache()
                    retry_count += 1
                    continue

                raise AppError(
                    code=ErrorCode.AUTH_INVALID,
                    http_status=401,
                    message="Invalid authentication token",
                )

            # Verify JWT signature using the key
            decoded = jwt.decode(
                token,
                matching_key,
                algorithms=["RS256", "ES256"],
                options={
                    "verify_signature": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "require_exp": True,
                },
                issuer=settings.CLERK_ISSUER,
                audience=settings.CLERK_AUDIENCE,
            )

            # Extract claims and validate required fields
            if not decoded.get("sub"):
                logger.warning("JWT missing 'sub' claim")
                raise AppError(
                    code=ErrorCode.AUTH_INVALID,
                    http_status=401,
                    message="Invalid authentication token",
                )

            # Return typed decoded token
            return DecodedToken(
                sub=decoded["sub"],
                email=decoded.get("email"),
                name=decoded.get("name"),
                iss=decoded["iss"],
                aud=decoded["aud"],
                exp=decoded["exp"],
            )

        except JWSSignatureError as e:
            logger.warning(f"JWT signature verification failed: {e}")
            if retry_count < max_retries:
                logger.info("JWKS refresh: retrying due to signature mismatch")
                invalidate_jwks_cache()
                retry_count += 1
                continue

            raise AppError(
                code=ErrorCode.AUTH_INVALID,
                http_status=401,
                message="Invalid authentication token",
            ) from e

        except JWTClaimsError as e:
            logger.warning(f"JWT claims validation failed: {e}")
            if "exp" in str(e).lower():
                raise AppError(
                    code=ErrorCode.AUTH_INVALID,
                    http_status=401,
                    message="Authentication token expired",
                ) from e
            raise AppError(
                code=ErrorCode.AUTH_INVALID,
                http_status=401,
                message="Invalid authentication token",
            ) from e

        except JWTError as e:
            logger.warning(f"JWT verification error: {e}")
            raise AppError(
                code=ErrorCode.AUTH_INVALID,
                http_status=401,
                message="Invalid authentication token",
            ) from e
