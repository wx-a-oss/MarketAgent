"""
Helpers to build indicator models populated with Finnhub data.

The fetcher composes the low-level `FinnhubClient` with the datamodel
definitions so callers only need a stock symbol to obtain indicators.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple

from market_agent.datamodel.indicators import (
    StockAnalysisIndicators,
    StockBaseIndicators,
)

from .finnhub_client import FinnhubClient


class FinnhubIndicatorFetcher:
    """Populate indicator models using Finnhub responses."""

    def __init__(self, client: FinnhubClient):
        self._client = client

    def build_base_indicators(self, symbol: str) -> StockBaseIndicators:
        """Fetch quote/profile data and map it into a basic indicator model."""
        quote = self._client.quote(symbol)
        profile = self._client.company_profile(symbol)

        extra: Dict[str, Any] = {}
        prev_close = self._to_optional_float(quote.get("pc"))
        if prev_close is not None:
            extra["previous_close"] = prev_close
        timestamp = quote.get("t")
        if timestamp is not None:
            extra["quote_timestamp"] = timestamp

        return StockBaseIndicators(
            symbol=symbol,
            open_price=self._to_optional_float(quote.get("o")),
            high_price=self._to_optional_float(quote.get("h")),
            low_price=self._to_optional_float(quote.get("l")),
            close_price=self._to_optional_float(quote.get("c")),
            volume=self._to_optional_int(quote.get("v")),
            market_cap=self._to_optional_float(profile.get("marketCapitalization")),
            extra=extra,
        )

    def build_analysis_indicators(self, symbol: str) -> StockAnalysisIndicators:
        """Fetch financial metrics and recommendations for analysis indicators."""
        financials = self._client.basic_financials(symbol)
        metrics: Dict[str, Any] = financials.get("metric") or {}
        recommendations = self._client.recommendation_trends(symbol)

        moving_averages = self._extract_moving_averages(metrics)
        recommendation_summary = self._summarise_recommendation(recommendations)

        extra: Dict[str, Any] = {}
        if recommendation_summary:
            latest_row = self._latest_row(recommendations)
            if latest_row:
                extra["recommendation_counts"] = {
                    key: latest_row.get(key)
                    for key in (
                        "strongBuy",
                        "buy",
                        "hold",
                        "sell",
                        "strongSell",
                    )
                    if latest_row.get(key) is not None
                }

        return StockAnalysisIndicators(
            symbol=symbol,
            moving_averages=moving_averages,
            rsi=self._to_optional_float(
                metrics.get("14DayRSI") or metrics.get("RSI")
            ),
            macd=self._to_optional_float(metrics.get("MACD")),
            beta=self._to_optional_float(metrics.get("beta")),
            recommendation=recommendation_summary,
            extra=extra,
        )

    @staticmethod
    def _extract_moving_averages(metrics: Dict[str, Any]) -> Dict[str, float]:
        keys = ("10DayAverageTradingVolume", "50DayMA", "200DayMA")
        result: Dict[str, float] = {}
        for key in keys:
            value = metrics.get(key)
            if value is None:
                continue
            maybe_float = FinnhubIndicatorFetcher._to_optional_float(value)
            if maybe_float is not None:
                result[key] = maybe_float
        return result

    @staticmethod
    def _summarise_recommendation(rows: Iterable[Dict[str, Any]]) -> Optional[str]:
        latest_row = FinnhubIndicatorFetcher._latest_row(rows)
        if not latest_row:
            return None

        buckets: Tuple[Tuple[str, str], ...] = (
            ("strongBuy", "Strong Buy"),
            ("buy", "Buy"),
            ("hold", "Hold"),
            ("sell", "Sell"),
            ("strongSell", "Strong Sell"),
        )

        scored: Dict[str, float] = {}
        for key, label in buckets:
            value = latest_row.get(key)
            if value is None:
                continue
            numeric = FinnhubIndicatorFetcher._to_optional_float(value)
            if numeric is not None:
                scored[label] = numeric

        if not scored:
            return None

        return max(scored.items(), key=lambda item: item[1])[0]

    @staticmethod
    def _latest_row(rows: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        latest_row: Optional[Dict[str, Any]] = None
        latest_period = ""
        for row in rows:
            period = str(row.get("period", ""))
            if period >= latest_period:
                latest_period = period
                latest_row = row
        return latest_row

    @staticmethod
    def _to_optional_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_optional_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
