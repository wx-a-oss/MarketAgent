"""Person datamodels for future expansion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Person:
    name: str
    role: Optional[str] = None
    description: Optional[str] = None
