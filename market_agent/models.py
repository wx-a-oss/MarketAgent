from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class Quote(BaseModel):
    open: Optional[float] = Field(None, description="Open")
    high: Optional[float] = Field(None, description="High")
    low: Optional[float] = Field(None, description="Low")
    current: Optional[float] = Field(None, description="Current price")
    prev_close: Optional[float] = Field(None, description="Previous close")
    change: Optional[float] = Field(None, description="Change")
    percent: Optional[float] = Field(None, description="Percent")

class CompanyProfile(BaseModel):
    name: Optional[str]
    ticker: Optional[str]
    exchange: Optional[str]
    ipo: Optional[str]
    market_cap: Optional[float]
    industry: Optional[str]
    weburl: Optional[str]
    country: Optional[str]
    logo: Optional[str]

class Metrics(BaseModel):
    metric: Dict[str, Any] = {}
    metricType: Optional[str] = None

class Recommendation(BaseModel):
    period: Optional[str]
    buy: Optional[int]
    hold: Optional[int]
    sell: Optional[int]
    strongBuy: Optional[int]
    strongSell: Optional[int]

class EpsItem(BaseModel):
    period: Optional[str]
    actual: Optional[float]
    estimate: Optional[float]

class StockOverview(BaseModel):
    symbol: str
    profile: CompanyProfile
    quote: Quote
    metrics: Optional[Metrics] = None
    recommendations: List[Recommendation] = []
    eps: List[EpsItem] = []
    peers: List[str] = []
    raw: Dict[str, Any] = {}