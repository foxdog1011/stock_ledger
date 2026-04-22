"""Knowledge base MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ._common import DB_PATH


def register(mcp: FastMCP) -> None:
    """Register knowledge base tools on the given MCP server instance."""

    @mcp.tool()
    def search_knowledge(query: str, limit: int = 10) -> dict[str, Any]:
        """Search the knowledge base using full-text search.

        Searches across article titles, summaries, and content for matching
        keywords. Useful for finding previously ingested articles about
        specific topics, companies, or market themes.

        Args:
            query: Search keywords (e.g. "MEMS 石英", "AI semiconductor", "台積電 CoWoS").
            limit: Max results to return (default 10).

        Returns:
            {"entries": [...], "count": int, "query": str}
        """
        try:
            from domain.knowledge.repository import search_entries, init_knowledge_tables
            init_knowledge_tables(DB_PATH)
            entries = search_entries(DB_PATH, query, limit)
            return {
                "query": query,
                "count": len(entries),
                "entries": [
                    {
                        "id": e.id,
                        "title": e.title,
                        "url": e.url,
                        "summary": e.summary,
                        "tickers": e.tickers,
                        "tags": e.tags,
                        "quality_tier": e.quality_tier,
                        "created_at": e.created_at,
                    }
                    for e in entries
                ],
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "search_knowledge"}

    @mcp.tool()
    def list_knowledge(
        ticker: str | None = None,
        tag: str | None = None,
        quality: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List knowledge base entries with optional filters.

        Browse ingested articles filtered by stock ticker, topic tag,
        or quality tier. Returns a paginated list ordered by newest first.

        Args:
            ticker: Filter by stock ticker (e.g. "2330", "AMD").
            tag: Filter by topic tag (e.g. "半導體", "AI").
            quality: Filter by quality tier ("high", "medium", "low", "unreviewed").
            limit: Max entries to return (default 20).

        Returns:
            {"entries": [...], "total": int}
        """
        try:
            from domain.knowledge.repository import list_entries, count_entries, init_knowledge_tables
            init_knowledge_tables(DB_PATH)
            entries = list_entries(DB_PATH, limit=limit, ticker=ticker, tag=tag, quality_tier=quality)
            total = count_entries(DB_PATH)
            return {
                "total": total,
                "count": len(entries),
                "entries": [
                    {
                        "id": e.id,
                        "title": e.title,
                        "url": e.url,
                        "summary": e.summary,
                        "tickers": e.tickers,
                        "tags": e.tags,
                        "quality_tier": e.quality_tier,
                        "created_at": e.created_at,
                    }
                    for e in entries
                ],
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "list_knowledge"}

    @mcp.tool()
    def get_knowledge_entry(entry_id: int) -> dict[str, Any]:
        """Get full details of a knowledge base entry including content.

        Returns the complete article with original content, analysis results,
        and Obsidian vault path. Useful for reading the full text of an
        article found via search or list.

        Args:
            entry_id: The integer ID of the knowledge entry.

        Returns:
            Full entry dict with content, bull_case, bear_case, etc.
        """
        try:
            from domain.knowledge.repository import get_entry, init_knowledge_tables
            init_knowledge_tables(DB_PATH)
            entry = get_entry(DB_PATH, entry_id)
            if not entry:
                return {"error": f"Entry {entry_id} not found"}
            return {
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
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "get_knowledge_entry"}

    @mcp.tool()
    def knowledge_stats() -> dict[str, Any]:
        """Get aggregate statistics about the knowledge base.

        Returns total count, breakdown by quality tier, source type,
        and top mentioned tickers and tags. Useful for understanding
        the current state and coverage of your research collection.

        Returns:
            Stats dict with total, by_quality, by_source, top_tickers, top_tags.
        """
        try:
            from domain.knowledge.repository import list_entries, count_entries, init_knowledge_tables
            init_knowledge_tables(DB_PATH)
            total = count_entries(DB_PATH)
            entries = list_entries(DB_PATH, limit=9999)

            tier_counts: dict[str, int] = {}
            source_counts: dict[str, int] = {}
            all_tickers: dict[str, int] = {}
            all_tags: dict[str, int] = {}

            for e in entries:
                tier_counts[e.quality_tier] = tier_counts.get(e.quality_tier, 0) + 1
                source_counts[e.source_type] = source_counts.get(e.source_type, 0) + 1
                for t in e.tickers:
                    all_tickers[t] = all_tickers.get(t, 0) + 1
                for tag in e.tags:
                    all_tags[tag] = all_tags.get(tag, 0) + 1

            top_tickers = sorted(all_tickers.items(), key=lambda x: x[1], reverse=True)[:10]
            top_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)[:10]

            return {
                "total": total,
                "by_quality": tier_counts,
                "by_source": source_counts,
                "top_tickers": [{"ticker": t, "count": c} for t, c in top_tickers],
                "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "knowledge_stats"}

    @mcp.tool()
    def find_related_articles(entry_id: int, limit: int = 5) -> dict[str, Any]:
        """Find articles related to a given knowledge entry.

        Finds other articles that share the same tickers or tags as the
        specified entry. Useful for cross-referencing different perspectives
        on the same stock or topic.

        Args:
            entry_id: The ID of the reference entry.
            limit: Max related articles to return (default 5).

        Returns:
            {"reference": {...}, "related": [...], "count": int}
        """
        try:
            from domain.knowledge.repository import get_entry, list_entries, init_knowledge_tables
            init_knowledge_tables(DB_PATH)
            entry = get_entry(DB_PATH, entry_id)
            if not entry:
                return {"error": f"Entry {entry_id} not found"}

            # Find entries sharing tickers or tags
            related: list[dict] = []
            seen_ids = {entry_id}

            for ticker in entry.tickers:
                matches = list_entries(DB_PATH, limit=limit * 2, ticker=ticker)
                for m in matches:
                    if m.id not in seen_ids:
                        seen_ids.add(m.id)
                        shared = [t for t in m.tickers if t in entry.tickers]
                        shared_tags = [t for t in m.tags if t in entry.tags]
                        related.append({
                            "id": m.id,
                            "title": m.title,
                            "url": m.url,
                            "tickers": m.tickers,
                            "tags": m.tags,
                            "shared_tickers": shared,
                            "shared_tags": shared_tags,
                            "relevance": len(shared) + len(shared_tags),
                            "created_at": m.created_at,
                        })

            for tag in entry.tags:
                matches = list_entries(DB_PATH, limit=limit * 2, tag=tag)
                for m in matches:
                    if m.id not in seen_ids:
                        seen_ids.add(m.id)
                        shared = [t for t in m.tickers if t in entry.tickers]
                        shared_tags = [t for t in m.tags if t in entry.tags]
                        related.append({
                            "id": m.id,
                            "title": m.title,
                            "url": m.url,
                            "tickers": m.tickers,
                            "tags": m.tags,
                            "shared_tickers": shared,
                            "shared_tags": shared_tags,
                            "relevance": len(shared) + len(shared_tags),
                            "created_at": m.created_at,
                        })

            # Sort by relevance (shared tickers + tags count)
            related.sort(key=lambda x: x["relevance"], reverse=True)

            return {
                "reference": {
                    "id": entry.id,
                    "title": entry.title,
                    "tickers": entry.tickers,
                    "tags": entry.tags,
                },
                "related": related[:limit],
                "count": len(related[:limit]),
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "find_related_articles"}
