"""Shared data models and types for video generation endpoints."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


# ── Video generation request ──────────────────────────────────────────────────

class VideoRequest(BaseModel):
    symbol: str
    script: str = ""
    days: int = 7
    format: str = "landscape"   # "landscape" (1920x1080) | "shorts" (1080x1920)
    sector_name: str = ""        # e.g. "散熱族群"
    symbols: list[str] = []      # e.g. ["2230","3017","6245","8016"]


# ── Pick stock ────────────────────────────────────────────────────────────────

class SlotType(str, Enum):
    morning = "morning"
    afternoon = "afternoon"
    long_tuesday = "long_tuesday"
    long_friday = "long_friday"
    weekly_review = "weekly_review"
    sat_am = "sat_am"
    sat_pm = "sat_pm"
    sun_am = "sun_am"
    sun_pm = "sun_pm"


class PickStockRequest(BaseModel):
    slot: SlotType
    exclude_symbols: list[str] = []
    ignore_cooldown: bool = False
    cooldown_days: int | None = None


class ChipSummary(BaseModel):
    foreign_net: int
    trust_net: int
    dealer_net: int


class PickStockResponse(BaseModel):
    symbol: str
    title: str
    pick_reason: str
    chip_summary: ChipSummary
    data_date: str
    is_holiday_fallback: bool


class WeeklyReviewResponse(BaseModel):
    symbols: list[PickStockResponse]
    data_date: str
    is_holiday_fallback: bool


# ── n8n generate/upload ──────────────────────────────────────────────────────

class N8nGenerateRequest(BaseModel):
    symbol: str
    title: str
    slot: str = "morning"
    is_holiday_fallback: bool = False


class N8nGenerateResponse(BaseModel):
    video_path: str
    thumbnail_path: Optional[str] = None
    title: str
    description: str
    tags: list[str]
    script: str
    symbol: str
    slot: str


class N8nUploadRequest(BaseModel):
    video_path: str
    title: str
    description: str = ""
    tags: list[str] = []
    script: str = ""
    slot: str = "morning"
    privacy: str = "public"
    publish_time: Optional[str] = None  # e.g. "08:00", "14:30"
    thumbnail_path: Optional[str] = None
    symbol: str = ""
    data_date: str = ""  # YYYY-MM-DD, used for upload deduplication
    ignore_rate_limit: bool = False  # n8n can override rate limiting
    auto_comment: bool = True  # post channel-owner comment after upload
    force: bool = False  # skip duplicate detection; re-upload even if same symbol/slot/date exists


class N8nUploadResponse(BaseModel):
    video_id: str
    url: str
    title: str
    privacy: str
    publish_at: Optional[str] = None


# ── Sector endpoints ─────────────────────────────────────────────────────────

class PickSectorRequest(BaseModel):
    exclude_themes: list[str] = []
    force_refresh: bool = False
    ignore_cooldown: bool = False


class PickSectorResponse(BaseModel):
    sector_name: str
    symbols: list[dict]
    slot: str
    summary: dict


class GenerateSectorRequest(BaseModel):
    sector_name: str
    slot: str = "sector"
    format: str = "landscape"  # "landscape" (1920x1080) | "shorts" (1080x1920)


class GenerateSectorResponse(BaseModel):
    video_path: str
    thumbnail_path: Optional[str] = None
    title: str
    description: str
    tags: list[str]
    script: str
    sector_name: str
    slot: str


# ── TDCC pick ───────────────────────────────────────────────────────────────

class TdccSummary(BaseModel):
    big_holder_pct_change: float  # 大戶 (>=400張) percentage change
    retail_pct_change: float      # 散戶 (<=10張) percentage change
    latest_date: str
    prev_date: str


class TdccPickResponse(BaseModel):
    symbol: str
    title: str
    tdcc_summary: TdccSummary


# ── Rotation pick ───────────────────────────────────────────────────────────

class RotationPickResponse(BaseModel):
    buy_symbol: str
    buy_name: str
    buy_lots: int
    sell_symbol: str
    sell_name: str
    sell_lots: int
    title: str


# ── Weekly recap ───────────────────────────────────────────────────────────

class WeeklyRecapRequest(BaseModel):
    week_start: str = ""  # YYYY-MM-DD (Monday), defaults to last Monday


class WeeklyRecapResponse(BaseModel):
    video_path: str
    thumbnail_path: Optional[str] = None
    title: str
    description: str
    tags: list[str]
    script: str
    featured_symbols: list[str]
    week_start: str
    week_end: str


# ── Community post ─────────────────────────────────────────────────────────

class CommunityPostRequest(BaseModel):
    poll_question: str = "本週最強族群？"
    poll_options: list[str] = ["半導體", "金融", "傳產", "航運", "生技"]
    additional_text: str = ""


class CommunityPostResponse(BaseModel):
    status: str
    message: str
    suggested_content: dict


# ── Next-week outlook ─────────────────────────────────────────────────────

class OutlookRequest(BaseModel):
    format: str = "shorts"  # shorts or landscape


class OutlookResponse(BaseModel):
    video_path: str
    thumbnail_path: Optional[str] = None
    title: str
    description: str
    tags: list[str]
    script: str
    featured_symbols: list[str]


# ── Check missed ─────────────────────────────────────────────────────────

class CheckMissedResponse(BaseModel):
    today: str
    day_of_week: str
    expected_slots: list[dict]
    uploaded_slots: list[dict]
    missed_slots: list[dict]
    recovered: list[dict]
    errors: list[dict]
