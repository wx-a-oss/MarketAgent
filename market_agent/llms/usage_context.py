"""Thread-local context for LLM usage tracking.

Set context before calling a provider so the low-level call can log
which module/purpose/company triggered the request.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager

_ctx = threading.local()


def set_usage_context(
    *, purpose: str, company_name: str | None = None, module: str | None = None,
) -> None:
    _ctx.purpose = purpose
    _ctx.company_name = company_name
    _ctx.module = module


def get_usage_context() -> dict:
    return {
        "purpose": getattr(_ctx, "purpose", "unknown"),
        "company_name": getattr(_ctx, "company_name", None),
        "module": getattr(_ctx, "module", None),
    }


def clear_usage_context() -> None:
    for attr in ("purpose", "company_name", "module"):
        if hasattr(_ctx, attr):
            delattr(_ctx, attr)


@contextmanager
def usage_context(purpose: str, company_name: str | None = None, module: str | None = None):
    set_usage_context(purpose=purpose, company_name=company_name, module=module)
    try:
        yield
    finally:
        clear_usage_context()
