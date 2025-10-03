# api/auth_supabase.py
import os
from pathlib import Path
from typing import Any, Dict

import jwt
from dotenv import load_dotenv
from fastapi import Header, HTTPException, status
from jwt import PyJWTError

# Load env from CWD then repo root
load_dotenv()
if not os.getenv("SUPABASE_JWT_SECRET"):
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
if not SUPABASE_JWT_SECRET or not isinstance(SUPABASE_JWT_SECRET, str):
    raise RuntimeError(
        "Server misconfigured: SUPABASE_JWT_SECRET is missing. "
        "Copy it from Supabase -> Settings -> Auth -> JWT (legacy secret) into your .env"
    )


def _decode_token(token: str) -> Dict[str, Any]:
    """
    Enhanced JWT decoding with security validation (less strict for Supabase compatibility).
    """
    try:
        # Decode with essential validations - Supabase tokens may not have all standard claims
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            # Enable core validations
            options={
                "verify_exp": True,      # Verify expiration (essential)
                "verify_iat": False,     # Skip issued at (Supabase may not have it)
                "verify_nbf": False,     # Skip not before (Supabase may not have it)
                "verify_aud": False,     # Skip audience (Supabase may not have it)
                "verify_signature": True, # Always verify signature
            },
            # Don't require issuer/audience to be specific values for Supabase compatibility
            issuer=None,  # Allow any issuer
            audience=None,  # Allow any audience
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {str(e)}")
    except Exception as e:
        raise ValueError(f"Token validation failed: {str(e)}")

    if not isinstance(payload, dict):
        raise ValueError("Token payload was not a JSON object")

    # Validate required claims
    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("Token missing subject (sub) claim")

    # Validate token type if present (but don't fail if missing)
    token_type = payload.get("token_type")
    if token_type and token_type not in ["access", "bearer"]:
        raise ValueError(f"Invalid token type: {token_type}")

    # For Supabase tokens, be more lenient about issuer validation
    # Just log it if it's unexpected but don't fail
    issuer = payload.get("iss")
    if issuer and issuer not in ["supabase", "Supabase"]:
        # Don't fail, but this might indicate an issue
        pass

    return {"user_id": user_id, "claims": payload}


async def get_current_user(authorization: str | None = Header(default=None)) -> Dict[str, Any]:
    """Validate the Supabase JWT and return the user id plus claims."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    # Pre-validate token format for better performance
    if not validate_token_format(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format")

    try:
        info = _decode_token(token)
    except (PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}") from exc

    info["access_token"] = token
    return info


async def require_user(authorization: str | None = Header(default=None)) -> str:
    """Compatibility helper that returns just the user id."""
    user = await get_current_user(authorization=authorization)
    return user["user_id"]


def validate_token_format(token: str) -> bool:
    """
    Validate basic token format before decoding.
    Helps prevent unnecessary processing of malformed tokens.
    """
    if not token or not isinstance(token, str):
        return False

    # JWT should have 3 parts separated by dots
    parts = token.split('.')
    if len(parts) != 3:
        return False

    # Each part should be non-empty and base64url encoded (basic check)
    for part in parts:
        if not part or len(part) < 4:  # Minimum reasonable length for base64url
            return False

    return True


def get_token_expiration(token: str) -> float | None:
    """
    Extract token expiration time without full validation.
    Useful for client-side token management.
    """
    try:
        # Decode without verification to get expiration
        payload = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
            }
        )
        return payload.get("exp")
    except Exception:
        return None


def is_token_expired(token: str) -> bool:
    """
    Check if token is expired without full validation.
    """
    exp = get_token_expiration(token)
    if exp is None:
        return True  # If we can't get expiration, consider it expired

    import time
    return time.time() >= exp
