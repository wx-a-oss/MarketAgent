"""Backward-compatible re-exports. Types now live in market_agent.schemas.company."""

from market_agent.schemas.company import *  # noqa: F401,F403
from market_agent.schemas.company import Company

__all__ = ["Company"]
