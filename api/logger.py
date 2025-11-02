# api/logger.py
"""
Structured logging utility with request IDs and context.
"""

import logging
import sys
from typing import Optional
from contextvars import ContextVar

# Request context for tracking request IDs across async calls
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(name)

def set_request_id(request_id: str):
    """Set request ID for current context."""
    request_id_var.set(request_id)

def get_request_id() -> Optional[str]:
    """Get request ID from current context."""
    return request_id_var.get()

class RequestLogger(logging.LoggerAdapter):
    """Logger adapter that automatically includes request ID."""

    def process(self, msg, kwargs):
        request_id = get_request_id()
        if request_id:
            msg = f"[req:{request_id[:8]}] {msg}"
        return msg, kwargs
