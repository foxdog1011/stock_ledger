"""Knowledge ingestion and retrieval API.

POST /api/knowledge/ingest       — Ingest a URL (fetch + AI analyze + save to Obsidian)
POST /api/knowledge/ingest-text  — Ingest raw text (manual paste)
GET  /api/knowledge              — List knowledge entries
GET  /api/knowledge/{id}         — Get a single entry
GET  /api/knowledge/search       — Search by ticker or tag
GET  /api/knowledge/stats        — Knowledge base statistics
POST /api/knowledge/{id}/review  — Re-run AI review on an entry
POST /api/knowledge/{id}/debate  — Deep multi-agent debate (4 agents)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from domain.knowledge.fetcher import fetch_content
from domain.knowledge.analyzer import analyze_content
from domain.knowledge.obsidian import write_to_vault
from domain.knowledge.repository import (
    insert_entry,
    get_entry,
    get_by_url,
    list_entries,
    update_review,
    count_entries,
)

# Tracking params to strip for dedup (Threads, Twitter, UTM, etc.)
_TRACKING_PARAMS = {"xmt", "slof", "utm_source", "utm_medium", "utm_campaign",
                    "utm_content", "utm_term", "igshid", "s", "t", "ref"}

logger = logging.getLogger(__name__)
router = APIRouter()

_DB_PATH = os.environ.get("DB_PATH", "ledger.db")


def _get_db() -> str:
    return os.environ.get("DB_PATH", _DB_PATH)


def _check_api_key(x_api_key: str = Header(None, alias="X-API-Key")) -> None:
    """Validate API key for write endpoints (ingest, review, debate).

    Uses JARVIS_KEY env var. If not set, auth is disabled (local dev).
    """
    expected = os.environ.get("JARVIS_KEY", "").strip()
    if not expected:
        return  # No key configured = local dev mode, skip auth
    if x_api_key != expected:
        raise HTTPException(401, "Invalid or missing API key (X-API-Key header)")


# ── Request/Response models ─────────────────────────────────────────────────


class IngestURLRequest(BaseModel):
    url: str
    source_type: str = "auto"
    notes: str = ""


class IngestTextRequest(BaseModel):
    title: str
    content: str
    source_url: str = ""
    notes: str = ""
    tags: list[str] = []


class ReviewRequest(BaseModel):
    """Trigger AI re-review of an existing entry."""
    pass


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/knowledge/ingest", summary="Ingest a URL (GET shortcut for iOS)")
def ingest_url_get(
    request: Request,
    x_api_key: str = Header(None, alias="X-API-Key"),
) -> JSONResponse:
    """GET version for iOS Shortcuts — accepts url as query parameter.

    Uses raw query string to preserve '&' in target URLs (e.g. Threads URLs
    with ?xmt=...&slof=... would be split by FastAPI's normal parsing).
    """
    _check_api_key(x_api_key)
    raw_qs = str(request.url.query)
    if not raw_qs.startswith("url="):
        raise HTTPException(400, "Missing 'url' query parameter")
    # Everything after 'url=' is the target URL (may contain & from the target)
    target_url = raw_qs[4:]  # strip "url="
    # URL-decode percent-encoded characters
    from urllib.parse import unquote
    target_url = unquote(target_url)
    if not target_url:
        raise HTTPException(400, "Empty 'url' parameter")
    req = IngestURLRequest(url=target_url, source_type="auto", notes="")
    return _do_ingest(req, _get_db())


@router.post("/knowledge/ingest", summary="Ingest a URL into the knowledge base")
def ingest_url(
    req: IngestURLRequest,
    x_api_key: str = Header(None, alias="X-API-Key"),
) -> JSONResponse:
    _check_api_key(x_api_key)
    """Fetch content from URL, run AI analysis, save to DB + Obsidian vault.

    This is the main one-click ingestion endpoint. Supports Threads, Twitter/X,
    and any web page. Returns the analysis result with Bull/Bear cases.
    """
    return _do_ingest(req, _get_db())


def _normalize_url(url: str) -> str:
    """Strip tracking parameters from URL for dedup comparison."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    cleaned = {k: v for k, v in params.items() if k not in _TRACKING_PARAMS}
    clean_qs = urlencode(cleaned, doseq=True) if cleaned else ""
    return urlunparse(parsed._replace(query=clean_qs))


def _do_ingest(req: IngestURLRequest, db: str) -> JSONResponse:
    """Shared ingestion logic for both GET and POST endpoints."""
    # Normalize URL (strip tracking params) for dedup
    normalized = _normalize_url(req.url)

    # Check for duplicate using normalized URL
    existing = get_by_url(db, normalized)
    if existing:
        return JSONResponse({
            "status": "duplicate",
            "message": "此 URL 已經擷取過",
            "id": existing.id,
            "title": existing.title,
            "obsidian_path": existing.obsidian_path,
        })

    # Step 1: Fetch content
    logger.info("Ingesting URL: %s (source: %s)", req.url, req.source_type)
    fetched = fetch_content(req.url, req.source_type)

    if not fetched.text or len(fetched.text.strip()) < 20:
        raise HTTPException(400, "無法擷取足夠的內容。請確認 URL 是否正確。")

    # Step 2: Local analysis (regex tickers + keyword tags, no API calls)
    analysis = analyze_content(
        title=fetched.title,
        text=fetched.text,
        source_type=fetched.source_type,
        user_notes=req.notes,
    )

    # Step 3: Write to Obsidian vault
    obsidian_path = write_to_vault(
        title=analysis.title,
        url=normalized,
        source_type=fetched.source_type,
        summary=analysis.summary,
        content=fetched.text,
        tickers=analysis.tickers,
        tags=analysis.tags,
        bull_case=analysis.bull_case,
        bear_case=analysis.bear_case,
        audit_notes=analysis.audit_notes,
        quality_tier=analysis.quality_tier,
        quality_score=analysis.quality_score,
        author=fetched.author,
    )

    # Step 4: Save to database (use normalized URL for dedup)
    entry_id = insert_entry(
        db_path=db,
        url=normalized,
        source_type=fetched.source_type,
        title=analysis.title,
        content=fetched.text[:5000],
        summary=analysis.summary,
        tickers=analysis.tickers,
        tags=analysis.tags,
        quality_tier=analysis.quality_tier,
        bull_case=analysis.bull_case,
        bear_case=analysis.bear_case,
        audit_notes=analysis.audit_notes,
        quality_score=analysis.quality_score,
        obsidian_path=obsidian_path,
    )

    logger.info(
        "Ingested: id=%d title=%s tickers=%s",
        entry_id, analysis.title, analysis.tickers,
    )

    return JSONResponse({
        "status": "ok",
        "id": entry_id,
        "title": analysis.title,
        "summary": analysis.summary,
        "tickers": analysis.tickers,
        "tags": analysis.tags,
        "obsidian_path": obsidian_path,
    })


@router.post(
    "/knowledge/ingest-text",
    summary="Ingest raw text into the knowledge base",
)
def ingest_text(
    req: IngestTextRequest,
    x_api_key: str = Header(None, alias="X-API-Key"),
) -> JSONResponse:
    _check_api_key(x_api_key)
    """Manually paste text content for analysis. For content that can't be
    fetched by URL (e.g., screenshots, private messages)."""
    db = _get_db()

    if len(req.content.strip()) < 20:
        raise HTTPException(400, "內容太短，至少需要 20 個字。")

    analysis = analyze_content(
        title=req.title,
        text=req.content,
        source_type="manual",
        user_notes=req.notes,
    )

    # Merge user-provided tags with extracted tags
    all_tags = list(dict.fromkeys(req.tags + analysis.tags))

    obsidian_path = write_to_vault(
        title=analysis.title,
        url=req.source_url,
        source_type="manual",
        summary=analysis.summary,
        content=req.content,
        tickers=analysis.tickers,
        tags=all_tags,
        bull_case=analysis.bull_case,
        bear_case=analysis.bear_case,
        audit_notes=analysis.audit_notes,
        quality_tier=analysis.quality_tier,
        quality_score=analysis.quality_score,
    )

    entry_id = insert_entry(
        db_path=db,
        url=req.source_url,
        source_type="manual",
        title=analysis.title,
        content=req.content[:5000],
        summary=analysis.summary,
        tickers=analysis.tickers,
        tags=all_tags,
        quality_tier=analysis.quality_tier,
        bull_case=analysis.bull_case,
        bear_case=analysis.bear_case,
        audit_notes=analysis.audit_notes,
        quality_score=analysis.quality_score,
        obsidian_path=obsidian_path,
    )

    return JSONResponse({
        "status": "ok",
        "id": entry_id,
        "title": analysis.title,
        "summary": analysis.summary,
        "tickers": analysis.tickers,
        "tags": all_tags,
        "obsidian_path": obsidian_path,
    })


@router.get("/knowledge", summary="List knowledge entries")
def list_knowledge(
    limit: int = 50,
    offset: int = 0,
    ticker: Optional[str] = None,
    tag: Optional[str] = None,
    quality: Optional[str] = None,
) -> JSONResponse:
    """List knowledge entries with optional filters."""
    db = _get_db()
    entries = list_entries(db, limit, offset, ticker, tag, quality)
    total = count_entries(db)
    return JSONResponse({
        "total": total,
        "entries": [
            {
                "id": e.id,
                "url": e.url,
                "source_type": e.source_type,
                "title": e.title,
                "summary": e.summary,
                "tickers": e.tickers,
                "tags": e.tags,
                "quality_tier": e.quality_tier,
                "quality_score": e.quality_score,
                "created_at": e.created_at,
            }
            for e in entries
        ],
    })


@router.get("/knowledge/stats", summary="Knowledge base statistics")
def knowledge_stats() -> JSONResponse:
    """Return aggregate stats about the knowledge base."""
    db = _get_db()
    total = count_entries(db)
    entries = list_entries(db, limit=9999)

    tier_counts = {"high": 0, "medium": 0, "low": 0, "unreviewed": 0}
    all_tickers: dict[str, int] = {}
    all_tags: dict[str, int] = {}
    source_counts: dict[str, int] = {}

    for e in entries:
        tier_counts[e.quality_tier] = tier_counts.get(e.quality_tier, 0) + 1
        source_counts[e.source_type] = source_counts.get(e.source_type, 0) + 1
        for t in e.tickers:
            all_tickers[t] = all_tickers.get(t, 0) + 1
        for tag in e.tags:
            all_tags[tag] = all_tags.get(tag, 0) + 1

    # Top tickers and tags
    top_tickers = sorted(all_tickers.items(), key=lambda x: x[1], reverse=True)[:10]
    top_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)[:10]

    return JSONResponse({
        "total": total,
        "by_quality": tier_counts,
        "by_source": source_counts,
        "top_tickers": [{"ticker": t, "count": c} for t, c in top_tickers],
        "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
    })


@router.get("/knowledge/{entry_id}", summary="Get knowledge entry by ID")
def get_knowledge(entry_id: int) -> JSONResponse:
    """Get full details of a knowledge entry."""
    db = _get_db()
    entry = get_entry(db, entry_id)
    if not entry:
        raise HTTPException(404, "知識條目不存在")
    return JSONResponse({
        "id": entry.id,
        "url": entry.url,
        "source_type": entry.source_type,
        "title": entry.title,
        "content": entry.content,
        "summary": entry.summary,
        "tickers": entry.tickers,
        "tags": entry.tags,
        "quality_tier": entry.quality_tier,
        "quality_score": entry.quality_score,
        "bull_case": entry.bull_case,
        "bear_case": entry.bear_case,
        "audit_notes": entry.audit_notes,
        "created_at": entry.created_at,
        "obsidian_path": entry.obsidian_path,
    })


@router.post(
    "/knowledge/{entry_id}/review",
    summary="Re-run AI review on a knowledge entry",
)
def review_entry(
    entry_id: int,
    x_api_key: str = Header(None, alias="X-API-Key"),
) -> JSONResponse:
    _check_api_key(x_api_key)
    """Re-analyze an existing entry with the AI pipeline."""
    db = _get_db()
    entry = get_entry(db, entry_id)
    if not entry:
        raise HTTPException(404, "知識條目不存在")

    analysis = analyze_content(
        title=entry.title,
        text=entry.content,
        source_type=entry.source_type,
    )

    update_review(
        db_path=db,
        entry_id=entry_id,
        quality_tier=analysis.quality_tier,
        bull_case=analysis.bull_case,
        bear_case=analysis.bear_case,
        audit_notes=analysis.audit_notes,
        quality_score=analysis.quality_score,
    )

    return JSONResponse({
        "status": "ok",
        "id": entry_id,
        "quality_tier": analysis.quality_tier,
        "quality_score": analysis.quality_score,
        "bull_case": analysis.bull_case,
        "bear_case": analysis.bear_case,
        "audit_notes": analysis.audit_notes,
    })


@router.post(
    "/knowledge/{entry_id}/debate",
    summary="Run deep multi-agent debate on a knowledge entry",
)
def debate_entry(
    entry_id: int,
    x_api_key: str = Header(None, alias="X-API-Key"),
) -> JSONResponse:
    _check_api_key(x_api_key)
    """Run the 4-agent debate pipeline (Extractor → Bull → Bear → Auditor).

    This is the deep review mode — more thorough than /review but uses
    4x the API calls. Use for important articles that need rigorous validation.
    """
    from domain.knowledge.debate import run_debate

    db = _get_db()
    entry = get_entry(db, entry_id)
    if not entry:
        raise HTTPException(404, "知識條目不存在")

    try:
        result = run_debate(entry.title, entry.content)
    except Exception as exc:
        logger.exception("Debate failed for entry %d", entry_id)
        raise HTTPException(500, f"辯論分析失敗: {exc}") from exc

    # Update the entry with debate results
    bull_text = "\n".join(f"• {a}" for a in result.bull_arguments)
    bear_text = "\n".join(f"• {a}" for a in result.bear_arguments)
    blind_text = "\n".join(f"⚠ {b}" for b in result.blind_spots)
    audit_text = (
        f"裁決：{result.verdict}\n"
        f"矛盾：{'; '.join(result.contradictions) or '無'}\n"
        f"建議：{'; '.join(result.recommendations) or '無'}"
    )

    update_review(
        db_path=db,
        entry_id=entry_id,
        quality_tier=result.quality_tier,
        bull_case=bull_text,
        bear_case=f"{bear_text}\n\n盲點：\n{blind_text}",
        audit_notes=audit_text,
        quality_score=result.quality_score,
    )

    return JSONResponse({
        "status": "ok",
        "id": entry_id,
        "debate": {
            "extraction": {
                "key_claims": result.key_claims,
                "data_points": result.data_points,
                "tickers": result.tickers,
                "thesis": result.thesis,
            },
            "bull": {
                "arguments": result.bull_arguments,
                "confidence": result.bull_confidence,
            },
            "bear": {
                "arguments": result.bear_arguments,
                "blind_spots": result.blind_spots,
                "confidence": result.bear_confidence,
            },
            "auditor": {
                "quality_tier": result.quality_tier,
                "quality_score": result.quality_score,
                "verdict": result.verdict,
                "contradictions": result.contradictions,
                "recommendations": result.recommendations,
            },
        },
    })
