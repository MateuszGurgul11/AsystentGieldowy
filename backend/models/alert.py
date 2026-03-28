from pydantic import BaseModel
from typing import Literal
from datetime import datetime


class AlertResponse(BaseModel):
    id: str
    user_id: str
    event_id: str | None
    prediction_id: str | None
    type: str
    title: str
    body: str
    priority: str
    is_read: bool
    created_at: datetime


class AlertSettingsUpdate(BaseModel):
    twitter_trigger: bool | None = None
    news_trigger: bool | None = None
    rsi_alert: bool | None = None
    rsi_threshold_oversold: int | None = None
    rsi_threshold_overbought: int | None = None
    price_change_alert: bool | None = None
    price_change_threshold: float | None = None
    monitored_symbols: list[str] | None = None


class AlertSettingsResponse(BaseModel):
    user_id: str
    twitter_trigger: bool
    news_trigger: bool
    rsi_alert: bool
    rsi_threshold_oversold: int
    rsi_threshold_overbought: int
    price_change_alert: bool
    price_change_threshold: float
    monitored_symbols: list[str]
