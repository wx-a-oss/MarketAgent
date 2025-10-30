from typing import Optional

def pct(change: Optional[float], base: Optional[float]) -> Optional[float]:
    if change is None or base in (None, 0):
        return None
    try:
        return (change / base) * 100.0
    except Exception:
        return None