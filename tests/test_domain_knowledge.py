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
from domain.knowledge.analyzer import (
    _extract_tickers_regex,
    _extract_us_tickers,
    _extract_tags,
    analyze_content,
)
from domain.knowledge.obsidian import _sanitize_filename, _ticker_wikilink


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
        assert _detect_source("https://www.threads.com/@user/post/abc") == "threads"

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

    @pytest.fixture(autouse=True)
    def _reset_ticker_cache(self):
        """Ensure universe DB cache is cleared so regex-only fallback is used."""
        from domain.knowledge import analyzer as _mod
        _mod._KNOWN_TW_TICKERS = None
        yield
        _mod._KNOWN_TW_TICKERS = None

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
        text = "year 2026 or number 0001 or 999 or ticker 2330"
        tickers = _extract_tickers_regex(text)
        assert "2026" not in tickers  # filtered as year
        assert "0001" not in tickers  # too low
        assert "2330" in tickers  # valid ticker
        # 999 has only 3 digits, won't match \b\d{4}\b

    def test_extract_us_tickers(self) -> None:
        text = "AMD and NVDA are up today, INTC lagging"
        tickers = _extract_us_tickers(text)
        assert "AMD" in tickers
        assert "NVDA" in tickers
        assert "INTC" in tickers

    def test_expanded_us_tickers(self) -> None:
        text = "PLTR and CRWD are cybersecurity plays"
        tickers = _extract_us_tickers(text)
        assert "PLTR" in tickers
        assert "CRWD" in tickers

    def test_expanded_us_tickers_china_adrs(self) -> None:
        text = "BABA JD PDD are Chinese ADRs"
        tickers = _extract_us_tickers(text)
        assert "BABA" in tickers
        assert "JD" in tickers
        assert "PDD" in tickers

    def test_extract_tags(self) -> None:
        text = "台積電的半導體技術在AI領域領先"
        tags = _extract_tags(text)
        assert "半導體" in tags
        assert "AI" in tags

    def test_analyze_content_no_api(self) -> None:
        """analyze_content should work without any API key."""
        result = analyze_content(
            title="Test",
            text="台積電(2330)在AI晶片市場表現亮眼，AMD也持續成長",
            source_type="threads",
        )
        assert "2330" in result.tickers
        assert "AMD" in result.tickers
        assert "半導體" in result.tags
        assert result.quality_tier == "unreviewed"
        assert result.bull_case == ""  # no AI analysis


# ── Universe DB integration tests ──────────────────────────────────────────


class TestUniverseIntegration:
    """Tests for ticker validation and wikilinks using universe DB."""

    @pytest.fixture
    def universe_db(self):
        """Create a temp DB with company_master table and sample data."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        con = sqlite3.connect(path)
        con.execute("""
            CREATE TABLE company_master (
                symbol TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        con.executemany(
            "INSERT INTO company_master (symbol, name) VALUES (?, ?)",
            [("2330", "台積電"), ("2454", "聯發科"), ("3008", "大立光")],
        )
        con.commit()
        con.close()
        yield path
        os.unlink(path)

    def test_load_known_tickers(self, universe_db: str) -> None:
        from domain.knowledge.analyzer import _load_known_tickers
        tickers = _load_known_tickers(universe_db)
        assert "2330" in tickers
        assert "2454" in tickers
        assert "3008" in tickers

    def test_load_known_tickers_missing_db(self) -> None:
        from domain.knowledge.analyzer import _load_known_tickers
        result = _load_known_tickers("/nonexistent/path.db")
        assert result == set()

    def test_extract_tickers_filtered_by_universe(self, universe_db: str) -> None:
        """When universe DB is available, only known tickers are returned."""
        from domain.knowledge import analyzer as _mod
        # Pre-load the known tickers from our test DB
        _mod._KNOWN_TW_TICKERS = _mod._load_known_tickers(universe_db)
        try:
            text = "2330 and 2454 are known, but 1234 is not in universe"
            tickers = _extract_tickers_regex(text)
            assert "2330" in tickers
            assert "2454" in tickers
            assert "1234" not in tickers
        finally:
            _mod._KNOWN_TW_TICKERS = None  # reset global cache

    def test_wikilink_from_universe_db(self, universe_db: str) -> None:
        """Wikilinks should pick up names from universe DB."""
        from domain.knowledge import obsidian as _obs_mod
        _obs_mod._TICKER_NAMES_CACHE = None  # reset cache
        with patch.dict(os.environ, {"DB_PATH": universe_db}):
            _obs_mod._TICKER_NAMES_CACHE = None  # force reload
            link = _ticker_wikilink("3008")
            assert link == "[[3008-大立光]]"
        _obs_mod._TICKER_NAMES_CACHE = None  # reset

    def test_wikilink_fallback_without_db(self) -> None:
        """Wikilinks should still work with hardcoded fallbacks."""
        from domain.knowledge import obsidian as _obs_mod
        _obs_mod._TICKER_NAMES_CACHE = None
        with patch.dict(os.environ, {"DB_PATH": "/nonexistent/path.db"}):
            _obs_mod._TICKER_NAMES_CACHE = None
            link = _ticker_wikilink("2330")
            assert link == "[[2330-台積電]]"
        _obs_mod._TICKER_NAMES_CACHE = None

    def test_wikilink_unknown_ticker(self) -> None:
        """Unknown tickers should get plain wikilinks."""
        from domain.knowledge import obsidian as _obs_mod
        _obs_mod._TICKER_NAMES_CACHE = None
        with patch.dict(os.environ, {"DB_PATH": "/nonexistent/path.db"}):
            _obs_mod._TICKER_NAMES_CACHE = None
            link = _ticker_wikilink("9999")
            assert link == "[[9999]]"
        _obs_mod._TICKER_NAMES_CACHE = None


# ── Search tests ──────────────────────────────────────────────────────────


class TestSearch:

    def test_fts_search(self, db_path: str) -> None:
        insert_entry(
            db_path=db_path, url="https://example.com/semi",
            source_type="web", title="TSMC Advanced Packaging",
            content="台積電的CoWoS先進封裝技術是AI晶片的關鍵",
            summary="CoWoS packaging", tickers=["2330"], tags=["半導體"],
            quality_tier="medium", bull_case="", bear_case="",
            audit_notes="", quality_score=0.5, obsidian_path="",
        )
        insert_entry(
            db_path=db_path, url="https://example.com/ev",
            source_type="web", title="Electric Vehicle Market",
            content="電動車市場成長快速，特斯拉和比亞迪競爭激烈",
            summary="EV market growth", tickers=[], tags=["電動車"],
            quality_tier="medium", bull_case="", bear_case="",
            audit_notes="", quality_score=0.5, obsidian_path="",
        )
        from domain.knowledge.repository import search_entries
        results = search_entries(db_path, "CoWoS")
        assert len(results) >= 1
        assert results[0].title == "TSMC Advanced Packaging"

        results2 = search_entries(db_path, "電動車")
        assert len(results2) >= 1

    def test_date_range_filter(self, db_path: str) -> None:
        insert_entry(
            db_path=db_path, url="https://example.com/date1",
            source_type="web", title="Old Article",
            content="Some old content here for testing",
            summary="Old", tickers=[], tags=[],
            quality_tier="medium", bull_case="", bear_case="",
            audit_notes="", quality_score=0.5, obsidian_path="",
        )
        entries = list_entries(db_path, created_after="2020-01-01")
        assert len(entries) >= 1
        entries_future = list_entries(db_path, created_after="2099-01-01")
        assert len(entries_future) == 0


# ── URL normalization tests ────────────────────────────────────────────────


class TestURLNormalization:

    def test_strips_tracking_params(self) -> None:
        from apps.api.routers.knowledge import _normalize_url
        url = "https://www.threads.com/@user/post/abc?xmt=tracking123&slof=1"
        normalized = _normalize_url(url)
        assert "xmt=" not in normalized
        assert "slof=" not in normalized
        assert "@user/post/abc" in normalized

    def test_preserves_meaningful_params(self) -> None:
        from apps.api.routers.knowledge import _normalize_url
        url = "https://example.com/article?page=2&sort=date"
        normalized = _normalize_url(url)
        assert "page=2" in normalized
        assert "sort=date" in normalized

    def test_strips_utm_params(self) -> None:
        from apps.api.routers.knowledge import _normalize_url
        url = "https://example.com/article?utm_source=twitter&utm_medium=social"
        normalized = _normalize_url(url)
        assert "utm_source" not in normalized
        assert "utm_medium" not in normalized


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
                bull_case="",
                bear_case="",
                audit_notes="",
                quality_tier="unreviewed",
                quality_score=0.0,
            )

        assert path.startswith("knowledge/")
        full_path = Path(vault_dir) / path
        assert full_path.exists()
        content = full_path.read_text(encoding="utf-8")
        assert "Test Article" in content
        assert "2330" in content
        assert "[[2330-台積電]]" in content  # wikilink
        assert "[[2454-聯發科]]" in content  # wikilink
        assert "#半導體" in content  # Obsidian tag
        assert "reviewed: false" in content  # Dataview field


# ── Debate module tests ─────────────────────────────────────────────────────


class TestDebateModule:

    def test_debate_result_dataclass(self) -> None:
        from domain.knowledge.debate import DebateResult
        result = DebateResult(
            key_claims=["claim1"],
            data_points=["data1"],
            tickers=["2330"],
            thesis="test thesis",
            bull_arguments=["bull1"],
            bull_confidence=0.8,
            bear_arguments=["bear1"],
            blind_spots=["blind1"],
            bear_confidence=0.6,
            quality_tier="high",
            quality_score=0.85,
            verdict="Good analysis",
            contradictions=[],
            recommendations=["verify data"],
        )
        assert result.quality_tier == "high"
        assert result.tickers == ["2330"]
        assert len(result.bull_arguments) == 1
        assert len(result.blind_spots) == 1

    def test_debate_endpoint_not_found(self, db_path: str) -> None:
        """Debate on nonexistent entry should 404."""
        from fastapi.testclient import TestClient
        from apps.api.main import app

        os.environ["DB_PATH"] = db_path
        env = {k: v for k, v in os.environ.items() if k != "JARVIS_KEY"}
        with patch.dict(os.environ, env, clear=True):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/api/knowledge/99999/debate")
            assert resp.status_code == 404


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

        env = {k: v for k, v in os.environ.items() if k != "JARVIS_KEY"}
        with patch.dict(os.environ, env, clear=True):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/api/knowledge/ingest-text", json={
                "title": "Test",
                "content": "Too short",
            })
            assert resp.status_code == 400

    def test_ingest_text_rejected_without_key(self, db_path: str) -> None:
        """Write endpoints require X-API-Key when JARVIS_KEY is set."""
        from fastapi.testclient import TestClient
        from apps.api.main import app

        with patch.dict(os.environ, {"JARVIS_KEY": "test-secret-key"}):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/api/knowledge/ingest-text", json={
                "title": "Test",
                "content": "This is a sufficiently long content for ingestion testing purposes.",
            })
            assert resp.status_code == 401

    def test_ingest_text_accepted_with_key(self, db_path: str) -> None:
        """Write endpoints succeed with correct X-API-Key."""
        from fastapi.testclient import TestClient
        from apps.api.main import app

        with patch.dict(os.environ, {"JARVIS_KEY": "test-secret-key"}):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/knowledge/ingest-text",
                json={
                    "title": "Test",
                    "content": "This is a sufficiently long content for ingestion testing purposes.",
                },
                headers={"X-API-Key": "test-secret-key"},
            )
            # Should not be 401 (may be 500 if OpenAI key not set, that's fine)
            assert resp.status_code != 401

    def test_read_endpoints_no_auth_needed(self, db_path: str) -> None:
        """Read endpoints work without API key even when JARVIS_KEY is set."""
        from fastapi.testclient import TestClient
        from apps.api.main import app

        with patch.dict(os.environ, {"JARVIS_KEY": "test-secret-key"}):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/knowledge")
            assert resp.status_code == 200, f"list got {resp.status_code}: {resp.text[:500]}"
            resp2 = client.get("/api/knowledge/stats")
            assert resp2.status_code == 200, f"stats got {resp2.status_code}: {resp2.text[:500]}"
