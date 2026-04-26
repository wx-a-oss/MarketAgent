"""Company datamodels for future expansion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Company:
    name: str
    ticker: Optional[str] = None
    description: Optional[str] = None
