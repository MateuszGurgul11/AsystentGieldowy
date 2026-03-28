from pydantic import BaseModel
from typing import Literal
from datetime import datetime


class Scenario(BaseModel):
    id: str                    # "A", "B", "C", "D"
    label: str
    probability: float
    description: str
    affected_assets: dict[str, float]  # {"BTC": -12.0, "ETH": -8.0}
    timeframe: str
    confidence: Literal["low", "medium", "high"]


class RecommendationStep(BaseModel):
    symbol: str
    action: Literal["BUY", "SELL", "HOLD"]
    quantity_pct: float | None = None   # % portfela
    amount_pln: float | None = None
    price_target: float | None = None
    note: str | None = None


class Recommendation(BaseModel):
    action: Literal["BUY", "SELL", "HOLD", "REDUCE_RISK", "WAIT"]
    rationale: str
    steps: list[RecommendationStep]


class PredictionResponse(BaseModel):
    id: str
    event_id: str | None
    symbol: str | None
    scenarios: list[Scenario]
    recommendation: Recommendation
    llm_reasoning: str | None
    confidence: str
    created_at: datetime
    verified_at: datetime | None
    actual_outcome: str | None
    accuracy_score: float | None


class EventResponse(BaseModel):
    id: str
    source: str
    author: str | None
    content: str
    url: str | None
    relevance_score: float
    affected_assets: list[str]
    detected_at: datetime
