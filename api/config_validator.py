# api/config_validator.py
"""
Startup configuration validator - fails fast when required env vars are missing.
"""

import os
import sys
from typing import List, Tuple


def validate_required_env_vars() -> Tuple[bool, List[str]]:
    """
    Validate that all required environment variables are set.

    Returns:
        Tuple of (is_valid, list_of_missing_vars)
    """
    required_vars = [
        "SUPABASE_URL",
        ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_ROLE"),  # Either one is fine
    ]

    missing = []

    for var in required_vars:
        if isinstance(var, tuple):
            # Check if at least one of the alternatives is set
            if not any(os.getenv(v) for v in var):
                missing.append(f"{var[0]} or {var[1]}")
        else:
            if not os.getenv(var):
                missing.append(var)

    return len(missing) == 0, missing


def validate_optional_features():
    """
    Check optional feature configurations and print warnings.
    """
    warnings = []

    # Gemini API for worksheet field detection
    if not os.getenv("GOOGLE_API_KEY"):
        warnings.append(
            "GOOGLE_API_KEY not set - worksheet field detection will be unavailable"
        )

    # JWKS URL for JWT verification
    if not os.getenv("SUPABASE_JWKS_URL") and not os.getenv("SUPABASE_URL"):
        warnings.append(
            "SUPABASE_JWKS_URL not set - JWT verification may fail"
        )

    return warnings


def validate_startup_config(exit_on_failure: bool = True) -> bool:
    """
    Run all startup validation checks.

    Args:
        exit_on_failure: If True, sys.exit(1) on validation failure

    Returns:
        True if all required configs are valid
    """
    print("=" * 60)
    print("[CONFIG] Validating startup configuration...")
    print("=" * 60)

    # Check required variables
    is_valid, missing = validate_required_env_vars()

    if not is_valid:
        print("\n[ERROR] CONFIGURATION ERROR: Missing required environment variables:")
        for var in missing:
            print(f"   - {var}")
        print("\nThe application cannot start without these variables.")
        print("Please set them in your .env file or environment.\n")

        if exit_on_failure:
            sys.exit(1)
        return False

    print("[OK] All required environment variables are set")

    # Check optional features
    warnings = validate_optional_features()
    if warnings:
        print("\n[WARNING] Optional feature warnings:")
        for warning in warnings:
            print(f"   - {warning}")

    print("\n" + "=" * 60)
    print("[OK] Configuration validation complete")
    print("=" * 60 + "\n")

    return True


if __name__ == "__main__":
    # Can be run standalone to check config
    validate_startup_config(exit_on_failure=False)
