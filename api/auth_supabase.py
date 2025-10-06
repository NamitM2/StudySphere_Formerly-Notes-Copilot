# api/auth_supabase.py
import os, time, httpx
from typing import Dict, Any
from fastapi import Header, HTTPException, status, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt  # python-jose

# ---- Config ----
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL") or (
    f"{SUPABASE_URL}/auth/v1/keys" if SUPABASE_URL else ""
)
LEGACY_HS256_SECRET = os.getenv("SUPABASE_JWT_SECRET")  # optional; for legacy tokens only

if not SUPABASE_JWKS_URL:
    raise RuntimeError("Set SUPABASE_URL or SUPABASE_JWKS_URL for JWKS verification.")

# ---- Caches/consts ----
_JWKS_CACHE: Dict[str, Any] = {"keys": None, "ts": 0}
_JWKS_TTL = 600
security = HTTPBearer(auto_error=True)

# ---- Helpers ----
def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

def _basic_shape_ok(token: str) -> bool:
    if not isinstance(token, str): return False
    parts = token.split(".")
    return len(parts) == 3 and all(len(p) >= 4 for p in parts)

async def _get_jwks() -> Dict[str, Any]:
    now = time.time()
    if _JWKS_CACHE["keys"] and (now - _JWKS_CACHE["ts"] < _JWKS_TTL):
        return _JWKS_CACHE["keys"]
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(SUPABASE_JWKS_URL)
        r.raise_for_status()
        _JWKS_CACHE["keys"] = r.json()
        _JWKS_CACHE["ts"] = now
        return _JWKS_CACHE["keys"]

def _decode_hs256(token: str) -> Dict[str, Any]:
    if not LEGACY_HS256_SECRET:
        raise ValueError("HS256 secret not configured")
    # Legacy tokens often omit aud/iss; skip aud verification.
    return jwt.decode(
        token,
        LEGACY_HS256_SECRET,
        algorithms=["HS256"],
        options={"verify_aud": False},
    )

async def _decode_rs256(token: str) -> Dict[str, Any]:
    jwks = await _get_jwks()
    hdr = jwt.get_unverified_header(token)
    kid = hdr.get("kid")
    if not kid:
        raise ValueError("Missing kid in token header")
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not key:
        raise ValueError("Unknown key id")
    alg = key.get("alg", "RS256")
    return jwt.decode(token, key, algorithms=[alg], options={"verify_aud": False})

async def _decode_auto(token: str) -> Dict[str, Any]:
    """
    Prefer RS256 (JWKS). If header alg == HS256, and legacy secret is set,
    verify with HS256 as a fallback to support older tokens during migration.
    """
    try:
        hdr = jwt.get_unverified_header(token)
    except Exception as e:
        raise _bad(f"Invalid token header: {e}")

    alg = (hdr.get("alg") or "").upper()
    if alg == "HS256":
        # Legacy path
        if not LEGACY_HS256_SECRET:
            # No secret configured—don’t accept HS256
            raise _bad("HS256 token not allowed (legacy secret not configured)")
        try:
            return _decode_hs256(token)
        except Exception as e:
            raise _bad(f"Invalid legacy token: {e}")

    # Default/modern: RS256 via JWKS
    try:
        return await _decode_rs256(token)
    except Exception as e:
        # As a last resort, if RS256 failed but token says HS256 and secret exists, try HS256.
        if LEGACY_HS256_SECRET and alg == "HS256":
            try:
                return _decode_hs256(token)
            except Exception:
                pass
        raise _bad(f"Invalid token: {e}")

def _extract_sub(claims: Dict[str, Any]) -> str:
    sub = claims.get("sub") or claims.get("user_id")
    if not sub:
        raise _bad("Token missing subject (sub)")
    return sub

# ---- Public deps ----
async def get_current_user(authorization: str | None = Header(default=None)) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _bad("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not _basic_shape_ok(token):
        raise _bad("Invalid token format")
    claims = await _decode_auto(token)
    user_id = _extract_sub(claims)
    return {"user_id": user_id, "claims": claims, "access_token": token}

async def require_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> str:
    token = creds.credentials
    if not _basic_shape_ok(token):
        raise _bad("Invalid token format")
    claims = await _decode_auto(token)
    return _extract_sub(claims)
