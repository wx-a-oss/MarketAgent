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

    def build_base_indicators(
        self, symbol: str, *, include_analysis: bool = True
    ) -> StockBaseIndicators:
        """Fetch quote/profile data and map it into a basic indicator model."""
        quote = self._client.quote(symbol)
        profile = self._client.company_profile(symbol)
        financials = self._client.basic_financials(symbol)
        metrics: Dict[str, Any] = financials.get("metric") or {}
        recommendations = (
            self._client.recommendation_trends(symbol) if include_analysis else []
        )

        extra: Dict[str, Any] = {}
        prev_close = self._to_optional_float(quote.get("pc"))
        if prev_close is not None:
            extra["previous_close"] = prev_close
        timestamp = quote.get("t")
        if timestamp is not None:
            extra["quote_timestamp"] = timestamp

        market_cap = self._to_optional_float(profile.get("marketCapitalization"))
        beta = self._metric_float(metrics, "beta")
        short_interest_pct_float = self._metric_float(
            metrics,
            "shortPercent",
            "shortPercentFloat",
            "shortInterestPercentOfFloat",
        )
        cash_and_equivalents = self._metric_float(
            metrics,
            "cashAndCashEquivalents",
            "cashAndCashEquivalentsTTM",
            "cashAndCashEquivalentsAnnual",
            "totalCash",
        )
        total_debt = self._metric_float(
            metrics,
            "totalDebt",
            "totalDebtTTM",
            "totalDebtAnnual",
        )
        capex = self._metric_float(
            metrics,
            "capitalExpenditure",
            "capitalExpenditureTTM",
            "capitalExpenditureAnnual",
            "capexTTM",
        )
        operating_cash_flow = self._metric_float(
            metrics,
            "operatingCashFlow",
            "operatingCashFlowTTM",
            "operatingCashFlowAnnual",
        )
        revenue = self._metric_float(
            metrics,
            "revenueTTM",
            "totalRevenue",
            "totalRevenueTTM",
        )
        net_income = self._metric_float(
            metrics,
            "netIncome",
            "netIncomeTTM",
            "netIncomeCommonStockholders",
            "netIncomeCommon",
        )

        if metrics:
            extra.update(self._extract_metric_extras(metrics))

        if include_analysis:
            rsi = self._to_optional_float(
                metrics.get("14DayRSI") or metrics.get("RSI")
            )
            if rsi is not None:
                extra["rsi"] = rsi

            macd = self._to_optional_float(metrics.get("MACD"))
            if macd is not None:
                extra["macd"] = macd

            recommendation_summary = self._summarise_recommendation(recommendations)
            if recommendation_summary:
                extra["recommendation"] = recommendation_summary
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

        enterprise_value = None
        if market_cap is not None and total_debt is not None and cash_and_equivalents is not None:
            enterprise_value = market_cap + total_debt - cash_and_equivalents

        free_cash_flow = None
        if operating_cash_flow is not None and capex is not None:
            free_cash_flow = operating_cash_flow - capex

        fcf_margin = None
        if free_cash_flow is not None and revenue:
            fcf_margin = free_cash_flow / revenue

        cash_conversion = None
        if free_cash_flow is not None and net_income:
            cash_conversion = free_cash_flow / net_income

        return StockBaseIndicators(
            symbol=symbol,
            open_price=self._to_optional_float(quote.get("o")),
            high_price=self._to_optional_float(quote.get("h")),
            low_price=self._to_optional_float(quote.get("l")),
            close_price=self._to_optional_float(quote.get("c")),
            volume=self._to_optional_int(quote.get("v")),
            market_cap=market_cap,
            enterprise_value=enterprise_value,
            beta=beta,
            short_interest_pct_float=short_interest_pct_float,
            cash_and_equivalents=cash_and_equivalents,
            total_debt=total_debt,
            capex=capex,
            operating_cash_flow=operating_cash_flow,
            free_cash_flow=free_cash_flow,
            fcf_margin=fcf_margin,
            cash_conversion=cash_conversion,
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

    @staticmethod
    def _metric_value(value: Any) -> Optional[Any]:
        if value is None:
            return None
        numeric = FinnhubIndicatorFetcher._to_optional_float(value)
        return numeric if numeric is not None else value

    @staticmethod
    def _extract_metric_extras(metrics: Dict[str, Any]) -> Dict[str, Any]:
        keys = (
            "10DayAverageTradingVolume",
            "13WeekPriceReturnDaily",
            "26WeekPriceReturnDaily",
            "3MonthADReturnStd",
            "3MonthAverageTradingVolume",
            "52WeekHigh",
            "52WeekHighDate",
            "52WeekLow",
            "52WeekLowDate",
            "52WeekPriceReturnDaily",
            "5DayPriceReturnDaily",
            "beta",
            "bookValuePerShareAnnual",
            "bookValuePerShareQuarterly",
            "bookValueShareGrowth5Y",
            "capexCagr5Y",
            "cashFlowPerShareAnnual",
            "cashFlowPerShareQuarterly",
            "cashFlowPerShareTTM",
            "currentEv/freeCashFlowAnnual",
            "currentEv/freeCashFlowTTM",
            "currentRatioAnnual",
            "currentRatioQuarterly",
            "epsAnnual",
            "epsGrowth3Y",
            "epsGrowth5Y",
            "epsGrowthQuarterlyYoy",
            "epsGrowthTTMYoy",
            "epsInclExtraItemsAnnual",
            "epsInclExtraItemsTTM",
            "epsNormalizedAnnual",
            "epsTTM",
            "evRevenueTTM",
            "focfCagr5Y",
            "forwardPE",
            "grossMargin5Y",
            "grossMarginAnnual",
            "grossMarginTTM",
            "longTermDebt/equityAnnual",
            "longTermDebt/equityQuarterly",
            "marketCapitalization",
            "monthToDatePriceReturnDaily",
            "netIncomeEmployeeAnnual",
            "netIncomeEmployeeTTM",
            "netInterestCoverageAnnual",
            "netMarginGrowth5Y",
            "netProfitMargin5Y",
            "netProfitMarginAnnual",
            "netProfitMarginTTM",
            "operatingMargin5Y",
            "operatingMarginAnnual",
            "operatingMarginTTM",
            "payoutRatioAnnual",
            "peAnnual",
            "priceRelativeToS&P50013Week",
            "priceRelativeToS&P50026Week",
            "priceRelativeToS&P5004Week",
            "priceRelativeToS&P50052Week",
            "priceRelativeToS&P500Ytd",
            "revenueGrowth3Y",
            "revenueGrowth5Y",
            "revenueGrowthQuarterlyYoy",
            "revenueGrowthTTMYoy",
            "revenuePerShareAnnual",
            "revenuePerShareTTM",
            "revenueShareGrowth5Y",
            "tangibleBookValuePerShareAnnual",
            "tangibleBookValuePerShareQuarterly",
            "tbvCagr5Y",
            "totalDebt/totalEquityAnnual",
            "totalDebt/totalEquityQuarterly",
            "yearToDatePriceReturnDaily",
        )
        key_aliases = {
            "3MonthADReturnStd": "3MonthAvgDailyReturnStdDev",
        }
        filtered_keys = {"marketCapitalization"}
        extra: Dict[str, Any] = {}
        for key in keys:
            if key in filtered_keys:
                continue
            value = metrics.get(key)
            if value is None:
                continue
            parsed = FinnhubIndicatorFetcher._metric_value(value)
            if parsed is not None:
                extra[key_aliases.get(key, key)] = parsed
        return extra

    @staticmethod
    def _metric_float(metrics: Dict[str, Any], *keys: str) -> Optional[float]:
        for key in keys:
            if key not in metrics:
                continue
            value = FinnhubIndicatorFetcher._to_optional_float(metrics.get(key))
            if value is not None:
                return value
        return None
