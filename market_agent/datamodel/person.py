"""Backward-compatible re-exports. Types now live in market_agent.schemas.person."""

from market_agent.schemas.person import *  # noqa: F401,F403
from market_agent.schemas.person import Person

__all__ = ["Person"]
