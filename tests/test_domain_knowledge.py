"""Tests for the knowledge ingestion module."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from domain.knowledge.models import KnowledgeEntry, SourceType, QualityTier
from domain.knowledge.repository import (
    init_knowledge_tables,
    insert_entry,
    get_entry,
    get_by_url,
    list_entries,
    update_review,
    count_entries,
)
from domain.knowledge.fetcher import _detect_source, _TextExtractor
from domain.knowledge.analyzer import _extract_tickers_regex
from domain.knowledge.obsidian import _sanitize_filename


@pytest.fixture
def db_path():
    """Create a temp database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_knowledge_tables(path)
    yield path
    os.unlink(path)


@pytest.fixture
def vault_dir():
    """Create a temp vault directory."""
    d = tempfile.mkdtemp(prefix="test_vault_")
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


# ── Repository tests ────────────────────────────────────────────────────────


class TestRepository:

    def test_init_tables(self, db_path: str) -> None:
        con = sqlite3.connect(db_path)
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        con.close()
        assert "knowledge_entries" in tables

    def test_insert_and_get(self, db_path: str) -> None:
        entry_id = insert_entry(
            db_path=db_path,
            url="https://example.com/article1",
            source_type="web",
            title="Test Article",
            content="Some content about 2330 TSMC",
            summary="TSMC analysis",
            tickers=["2330"],
            tags=["半導體"],
            quality_tier="high",
            bull_case="Strong AI demand",
            bear_case="Geopolitical risk",
            audit_notes="No contradictions",
            quality_score=0.85,
            obsidian_path="knowledge/2026-04/test.md",
        )
        assert entry_id > 0

        entry = get_entry(db_path, entry_id)
        assert entry is not None
        assert entry.title == "Test Article"
        assert entry.tickers == ["2330"]
        assert entry.quality_score == 0.85

    def test_get_by_url(self, db_path: str) -> None:
        url = "https://threads.net/post/123"
        insert_entry(
            db_path=db_path, url=url, source_type="threads",
            title="T", content="C", summary="S", tickers=[], tags=[],
            quality_tier="medium", bull_case="", bear_case="",
            audit_notes="", quality_score=0.5, obsidian_path="",
        )
        entry = get_by_url(db_path, url)
        assert entry is not None
        assert entry.source_type == "threads"

    def test_get_by_url_missing(self, db_path: str) -> None:
        assert get_by_url(db_path, "https://nonexistent.com") is None

    def test_list_entries(self, db_path: str) -> None:
        for i in range(5):
            insert_entry(
                db_path=db_path, url=f"https://example.com/{i}",
                source_type="web", title=f"Article {i}",
                content=f"Content {i}", summary=f"Summary {i}",
                tickers=["2330"] if i % 2 == 0 else ["2454"],
                tags=["台股"], quality_tier="medium",
                bull_case="", bear_case="", audit_notes="",
                quality_score=0.5, obsidian_path="",
            )
        all_entries = list_entries(db_path)
        assert len(all_entries) == 5

        # Filter by ticker
        tsmc = list_entries(db_path, ticker="2330")
        assert len(tsmc) == 3  # entries 0, 2, 4

    def test_list_by_quality(self, db_path: str) -> None:
        insert_entry(
            db_path=db_path, url="https://a.com", source_type="web",
            title="High", content="C", summary="S", tickers=[], tags=[],
            quality_tier="high", bull_case="", bear_case="",
            audit_notes="", quality_score=0.9, obsidian_path="",
        )
        insert_entry(
            db_path=db_path, url="https://b.com", source_type="web",
            title="Low", content="C", summary="S", tickers=[], tags=[],
            quality_tier="low", bull_case="", bear_case="",
            audit_notes="", quality_score=0.2, obsidian_path="",
        )
        high = list_entries(db_path, quality_tier="high")
        assert len(high) == 1
        assert high[0].title == "High"

    def test_update_review(self, db_path: str) -> None:
        entry_id = insert_entry(
            db_path=db_path, url="https://c.com", source_type="web",
            title="T", content="C", summary="S", tickers=[], tags=[],
            quality_tier="unreviewed", bull_case="", bear_case="",
            audit_notes="", quality_score=0.0, obsidian_path="",
        )
        result = update_review(
            db_path, entry_id,
            quality_tier="high",
            bull_case="Updated bull",
            bear_case="Updated bear",
            audit_notes="Reviewed",
            quality_score=0.9,
        )
        assert result is True
        entry = get_entry(db_path, entry_id)
        assert entry is not None
        assert entry.quality_tier == "high"
        assert entry.bull_case == "Updated bull"

    def test_count(self, db_path: str) -> None:
        assert count_entries(db_path) == 0
        insert_entry(
            db_path=db_path, url="https://d.com", source_type="web",
            title="T", content="C", summary="S", tickers=[], tags=[],
            quality_tier="medium", bull_case="", bear_case="",
            audit_notes="", quality_score=0.5, obsidian_path="",
        )
        assert count_entries(db_path) == 1


# ── Fetcher tests ───────────────────────────────────────────────────────────


class TestFetcher:

    def test_detect_threads(self) -> None:
        assert _detect_source("https://www.threads.net/@user/post/abc") == "threads"

    def test_detect_twitter(self) -> None:
        assert _detect_source("https://x.com/user/status/123") == "twitter"
        assert _detect_source("https://twitter.com/user/status/123") == "twitter"

    def test_detect_web(self) -> None:
        assert _detect_source("https://example.com/article") == "web"

    def test_text_extractor(self) -> None:
        html = "<html><head><title>Test</title></head><body><p>Hello world</p><script>bad</script></body></html>"
        parser = _TextExtractor()
        parser.feed(html)
        text = parser.get_text()
        assert "Hello world" in text
        assert "bad" not in text
        assert parser.get_title() == "Test"


# ── Analyzer tests ──────────────────────────────────────────────────────────


class TestAnalyzer:

    def test_extract_tickers_regex(self) -> None:
        text = "台積電(2330)跟聯發科(2454)今天表現亮眼"
        tickers = _extract_tickers_regex(text)
        assert "2330" in tickers
        assert "2454" in tickers

    def test_extract_tickers_no_duplicates(self) -> None:
        text = "2330 is mentioned twice: 2330"
        tickers = _extract_tickers_regex(text)
        assert tickers.count("2330") == 1

    def test_extract_tickers_filters_invalid(self) -> None:
        text = "year 2026 or number 0001 or 999"
        tickers = _extract_tickers_regex(text)
        assert "2026" in tickers  # valid range
        assert "0001" not in tickers  # too low
        # 999 has only 3 digits, won't match \b\d{4}\b


# ── Obsidian tests ──────────────────────────────────────────────────────────


class TestObsidian:

    def test_sanitize_filename(self) -> None:
        assert _sanitize_filename('Test: "Article" <1>') == "Test Article 1"
        assert _sanitize_filename("") == "untitled"
        assert len(_sanitize_filename("x" * 200)) <= 80

    def test_write_to_vault(self, vault_dir: str) -> None:
        from domain.knowledge.obsidian import write_to_vault

        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": vault_dir}):
            path = write_to_vault(
                title="Test Article",
                url="https://example.com",
                source_type="web",
                summary="A test summary",
                content="Full article content here",
                tickers=["2330", "2454"],
                tags=["半導體", "AI"],
                bull_case="Strong demand",
                bear_case="Valuation risk",
                audit_notes="No issues",
                quality_tier="high",
                quality_score=0.9,
            )

        assert path.startswith("knowledge/")
        full_path = Path(vault_dir) / path
        assert full_path.exists()
        content = full_path.read_text(encoding="utf-8")
        assert "Test Article" in content
        assert "2330" in content
        assert "Strong demand" in content
        assert "Valuation risk" in content


# ── API integration tests ───────────────────────────────────────────────────


class TestKnowledgeAPI:
    """API tests that use a temp DB to avoid table-not-found errors."""

    @pytest.fixture(autouse=True)
    def _setup_db(self, db_path: str) -> None:
        """Point the knowledge router at the temp DB."""
        self._old_db = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = db_path

    def teardown_method(self) -> None:
        if self._old_db is not None:
            os.environ["DB_PATH"] = self._old_db
        elif "DB_PATH" in os.environ:
            del os.environ["DB_PATH"]

    def test_list_empty(self, db_path: str) -> None:
        from fastapi.testclient import TestClient
        from apps.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/knowledge")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "entries" in data

    def test_stats_endpoint(self, db_path: str) -> None:
        from fastapi.testclient import TestClient
        from apps.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/knowledge/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "by_quality" in data

    def test_get_nonexistent(self, db_path: str) -> None:
        from fastapi.testclient import TestClient
        from apps.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/knowledge/99999")
        assert resp.status_code == 404

    def test_ingest_text_too_short(self, db_path: str) -> None:
        from fastapi.testclient import TestClient
        from apps.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/knowledge/ingest-text", json={
            "title": "Test",
            "content": "Too short",
        })
        assert resp.status_code == 400
