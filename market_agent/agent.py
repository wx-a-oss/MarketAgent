from typing import Dict, Any
from .config import settings
from .datasources.finnhub_client import FinnhubClient
from .models import StockOverview, Quote, CompanyProfile, Metrics, Recommendation, EpsItem

class MarketAgent:
    def __init__(self, api_key: str | None = None):
        key = api_key or settings.require_api_key()
        self.finnhub = FinnhubClient(key)

    def check_stock(self, symbol: str, include_raw: bool = False) -> StockOverview:
        symbol = symbol.upper().strip()

        q = self.finnhub.quote(symbol)
        prof = self.finnhub.company_profile(symbol)
        met = self.finnhub.basic_financials(symbol, metric="all")
        rec = self.finnhub.recommendation_trends(symbol)
        eps = self.finnhub.earnings(symbol)
        peers = self.finnhub.peers(symbol)

        quote = Quote(
            open=q.get("o"),
            high=q.get("h"),
            low=q.get("l"),
            current=q.get("c"),
            prev_close=q.get("pc"),
            change=q.get("d"),
            percent=q.get("dp"),
        )

        profile = CompanyProfile(
            name=prof.get("name"),
            ticker=prof.get("ticker"),
            exchange=prof.get("exchange"),
            ipo=prof.get("ipo"),
            market_cap=prof.get("marketCapitalization"),
            industry=prof.get("finnhubIndustry"),
            weburl=prof.get("weburl"),
            country=prof.get("country"),
            logo=prof.get("logo"),
        )

        metrics = Metrics(**met) if isinstance(met, dict) else None

        recommendations = [Recommendation(**r) for r in (rec or []) if isinstance(r, dict)]
        eps_items = [
            EpsItem(
                period=item.get("period"),
                actual=item.get("actual"),
                estimate=item.get("estimate"),
            )
            for item in (eps.get("data") if isinstance(eps, dict) else [])
            if isinstance(item, dict)
        ]

        raw: Dict[str, Any] = {}
        if include_raw:
            raw = {
                "quote": q,
                "profile": prof,
                "metrics": met,
                "recommendations": rec,
                "eps": eps,
                "peers": peers,
            }

        return StockOverview(
            symbol=symbol,
            profile=profile,
            quote=quote,
            metrics=metrics,
            recommendations=recommendations,
            eps=eps_items,
            peers=peers or [],
            raw=raw,
        )