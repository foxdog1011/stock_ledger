"""Knowledge module data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SourceType(str, Enum):
    threads = "threads"
    twitter = "twitter"
    web = "web"
    manual = "manual"


class QualityTier(str, Enum):
    unreviewed = "unreviewed"
    low = "low"
    medium = "medium"
    high = "high"


@dataclass(frozen=True)
class KnowledgeEntry:
    """A single piece of ingested knowledge."""
    id: int
    url: str
    source_type: str
    title: str
    content: str
    summary: str
    tickers: list[str]
    tags: list[str]
    quality_tier: str
    bull_case: str
    bear_case: str
    audit_notes: str
    quality_score: float
    created_at: str
    obsidian_path: str


@dataclass(frozen=True)
class IngestRequest:
    """Input for the ingest endpoint."""
    url: str
    source_type: str = "auto"
    notes: str = ""


@dataclass(frozen=True)
class IngestResult:
    """Output from the ingest pipeline."""
    id: int
    url: str
    title: str
    summary: str
    tickers: list[str]
    tags: list[str]
    obsidian_path: str
    quality_tier: str
    quality_score: float
