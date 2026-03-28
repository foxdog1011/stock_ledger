"""Ingest My-TW-Coverage markdown reports into the research_* tables.

Usage:
    python scripts/ingest_coverage.py --repo-path data/My-TW-Coverage
    python scripts/ingest_coverage.py --repo-path data/My-TW-Coverage --db-path data/ledger.db
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Wikilink helpers
# ---------------------------------------------------------------------------

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]")


def strip_wikilinks(text: str) -> str:
    """Replace [[Entity]] or [[Entity|Label]] with plain Entity text."""
    return _WIKILINK_RE.sub(r"\1", text)


def extract_wikilinks(text: str) -> list[str]:
    """Return all wikilink targets found in text."""
    return _WIKILINK_RE.findall(text)


# ---------------------------------------------------------------------------
# Markdown section parsing
# ---------------------------------------------------------------------------

def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    """Split markdown lines into a dict keyed by ## heading text (lowercased)."""
    sections: dict[str, list[str]] = {}
    current_key: str | None = None
    for line in lines:
        if line.startswith("## "):
            current_key = line[3:].strip()
            sections[current_key] = []
        elif current_key is not None:
            sections[current_key].append(line)
    return sections


def _parse_business_overview(section_lines: list[str]) -> dict:
    """Parse 業務簡介 section for sector, market_cap, ev, description."""
    result: dict = {
        "sector": None,
        "market_cap": None,
        "ev": None,
        "description": None,
    }

    description_lines: list[str] = []
    in_description = False

    for line in section_lines:
        stripped = line.strip()

        # Bold key-value pairs like **板塊:** Technology
        if stripped.startswith("**板塊:"):
            value = re.sub(r"\*\*板塊:\*\*\s*", "", stripped).strip()
            result["sector"] = strip_wikilinks(value) or None
            in_description = False
            continue
        if stripped.startswith("**市值:"):
            raw = re.sub(r"\*\*市值:\*\*\s*", "", stripped).strip()
            # Remove trailing units like " 百萬台幣"
            numeric = re.sub(r"[^\d.]", "", raw.split()[0]) if raw else ""
            result["market_cap"] = float(numeric) if numeric else None
            in_description = False
            continue
        if stripped.startswith("**企業價值:"):
            raw = re.sub(r"\*\*企業價值:\*\*\s*", "", stripped).strip()
            numeric = re.sub(r"[^\d.]", "", raw.split()[0]) if raw else ""
            result["ev"] = float(numeric) if numeric else None
            in_description = False
            continue
        # Skip empty bold-key lines that aren't the ones above
        if stripped.startswith("**") and ":**" in stripped:
            in_description = False
            continue
        # A non-empty, non-key line signals a description paragraph
        if stripped and not stripped.startswith("#"):
            in_description = True
            description_lines.append(strip_wikilinks(stripped))
        elif not stripped and in_description:
            # Blank line ends description paragraph
            in_description = False

    if description_lines:
        result["description"] = " ".join(description_lines)
    return result


def _parse_supply_chain(section_lines: list[str]) -> list[dict]:
    """Parse 供應鏈位置 section, returning list of {direction, entity, role_note}."""
    entries: list[dict] = []
    current_direction: str | None = None

    for line in section_lines:
        stripped = line.strip()

        if re.search(r"\*\*上游", stripped):
            current_direction = "upstream"
            continue
        if re.search(r"\*\*下游", stripped):
            current_direction = "downstream"
            continue
        if stripped.startswith("**") and ":**" in stripped and current_direction is None:
            # Other bold sub-headings — skip direction tracking
            continue

        if current_direction and stripped.startswith("-"):
            # Extract all wikilinks from this bullet as entities
            entities = extract_wikilinks(stripped)
            # Derive a role note from the text before the first colon (strip markup)
            plain = strip_wikilinks(stripped)
            role_note_match = re.match(r"-\s*\*\*(.*?)\*\*\s*[：:](.*)", plain)
            role_note = role_note_match.group(1).strip() if role_note_match else None

            for entity in entities:
                entries.append({
                    "direction": current_direction,
                    "entity": entity,
                    "role_note": role_note,
                })

    return entries


def _parse_customers_suppliers(section_lines: list[str]) -> tuple[list[dict], list[dict]]:
    """Parse 主要客戶及供應商, returning (customers, suppliers) lists."""
    customers: list[dict] = []
    suppliers: list[dict] = []
    current_list: list[dict] | None = None

    for line in section_lines:
        stripped = line.strip()

        if stripped.startswith("### 主要客戶"):
            current_list = customers
            continue
        if stripped.startswith("### 主要供應商"):
            current_list = suppliers
            continue
        if stripped.startswith("### "):
            current_list = None
            continue

        if current_list is not None and stripped.startswith("-"):
            entities = extract_wikilinks(stripped)
            plain = strip_wikilinks(stripped)
            note_match = re.match(r"-\s*\*\*(.*?)\*\*\s*[：:](.*)", plain)
            note = note_match.group(2).strip() if note_match else None

            for entity in entities:
                current_list.append({"counterpart": entity, "note": note})

    return customers, suppliers


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------

def parse_report(md_path: Path) -> dict | None:
    """Parse a single coverage markdown file.  Returns None if ticker invalid."""
    stem = md_path.stem  # e.g. "2330_台積電"

    # Ticker must start with 4 digits
    ticker_match = re.match(r"^(\d{4})", stem)
    if not ticker_match:
        return None
    ticker = ticker_match.group(1)

    # Name is the part after the first underscore or space
    name_part = re.sub(r"^\d{4}[_\s]*", "", stem).strip() or stem
    name = name_part

    # Industry is the parent directory name
    industry = md_path.parent.name

    raw_markdown = md_path.read_text(encoding="utf-8")
    lines = raw_markdown.splitlines()
    sections = _split_sections(lines)

    overview_key = next((k for k in sections if "業務簡介" in k), None)
    supply_chain_key = next((k for k in sections if "供應鏈" in k), None)
    customers_key = next((k for k in sections if "客戶" in k and "供應商" in k), None)

    overview = _parse_business_overview(sections[overview_key]) if overview_key else {}
    supply_chain = _parse_supply_chain(sections[supply_chain_key]) if supply_chain_key else []
    customers, suppliers = (
        _parse_customers_suppliers(sections[customers_key])
        if customers_key
        else ([], [])
    )

    return {
        "ticker": ticker,
        "name": name,
        "industry": industry,
        "sector": overview.get("sector"),
        "market_cap": overview.get("market_cap"),
        "ev": overview.get("ev"),
        "description": overview.get("description"),
        "raw_markdown": raw_markdown,
        "supply_chain": supply_chain,
        "customers": customers,
        "suppliers": suppliers,
    }


# ---------------------------------------------------------------------------
# Database upsert helpers
# ---------------------------------------------------------------------------

def upsert_company(conn: sqlite3.Connection, data: dict) -> None:
    conn.execute(
        """
        INSERT INTO research_companies
            (ticker, name, sector, industry, market_cap, ev, description, raw_markdown, updated_at)
        VALUES
            (:ticker, :name, :sector, :industry, :market_cap, :ev, :description, :raw_markdown,
             datetime('now'))
        ON CONFLICT(ticker) DO UPDATE SET
            name         = excluded.name,
            sector       = excluded.sector,
            industry     = excluded.industry,
            market_cap   = excluded.market_cap,
            ev           = excluded.ev,
            description  = excluded.description,
            raw_markdown = excluded.raw_markdown,
            updated_at   = excluded.updated_at
        """,
        {
            "ticker":       data["ticker"],
            "name":         data["name"],
            "sector":       data.get("sector"),
            "industry":     data.get("industry"),
            "market_cap":   data.get("market_cap"),
            "ev":           data.get("ev"),
            "description":  data.get("description"),
            "raw_markdown": data.get("raw_markdown"),
        },
    )


def replace_supply_chain(conn: sqlite3.Connection, ticker: str, entries: list[dict]) -> int:
    conn.execute("DELETE FROM research_supply_chain WHERE ticker = ?", (ticker,))
    for entry in entries:
        conn.execute(
            "INSERT INTO research_supply_chain (ticker, direction, entity, role_note) "
            "VALUES (?, ?, ?, ?)",
            (ticker, entry["direction"], entry["entity"], entry.get("role_note")),
        )
    return len(entries)


def replace_customers(conn: sqlite3.Connection, ticker: str,
                      customers: list[dict], suppliers: list[dict]) -> int:
    conn.execute("DELETE FROM research_customers WHERE ticker = ?", (ticker,))
    count = 0
    for c in customers:
        conn.execute(
            "INSERT INTO research_customers (ticker, counterpart, is_customer, note) "
            "VALUES (?, ?, 1, ?)",
            (ticker, c["counterpart"], c.get("note")),
        )
        count += 1
    for s in suppliers:
        conn.execute(
            "INSERT INTO research_customers (ticker, counterpart, is_customer, note) "
            "VALUES (?, ?, 0, ?)",
            (ticker, s["counterpart"], s.get("note")),
        )
        count += 1
    return count


def insert_theme(conn: sqlite3.Connection, ticker: str, theme: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO research_themes (ticker, theme) VALUES (?, ?)",
        (ticker, theme),
    )


# ---------------------------------------------------------------------------
# Theme file parsing
# ---------------------------------------------------------------------------

def ingest_themes(conn: sqlite3.Connection, themes_dir: Path) -> int:
    """Parse theme files and insert ticker <-> theme associations."""
    count = 0
    if not themes_dir.is_dir():
        return count

    for theme_file in themes_dir.rglob("*.md"):
        theme_name = theme_file.stem  # e.g. "AI_伺服器"
        content = theme_file.read_text(encoding="utf-8")
        # Support both wikilink format [[2330 台積電]] and bold format **2330 台積電**
        tickers = re.findall(r"\[\[(\d{4})[^\]]*\]\]", content)
        if not tickers:
            tickers = re.findall(r"\*\*(\d{4})\s", content)
        for ticker in set(tickers):
            insert_theme(conn, ticker, theme_name)
            count += 1

    return count


# ---------------------------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------------------------

def ingest(repo_path: Path, db_path: Path) -> None:
    reports_dir = repo_path / "Pilot_Reports"
    if not reports_dir.is_dir():
        print(f"ERROR: Pilot_Reports directory not found at {reports_dir}", file=sys.stderr)
        sys.exit(1)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    # Ensure research tables exist (idempotent)
    _ensure_research_tables(conn)

    total_companies = 0
    total_supply_chain = 0
    total_customers = 0

    md_files = sorted(reports_dir.rglob("*.md"))
    if not md_files:
        print("WARNING: No markdown files found under Pilot_Reports/", file=sys.stderr)

    for md_path in md_files:
        data = parse_report(md_path)
        if data is None:
            continue

        with conn:
            upsert_company(conn, data)
            sc_count = replace_supply_chain(conn, data["ticker"], data["supply_chain"])
            cu_count = replace_customers(conn, data["ticker"], data["customers"], data["suppliers"])

        total_companies += 1
        total_supply_chain += sc_count
        total_customers += cu_count

        print(f"Ingested {data['ticker']} {data['name']} ({data['industry']})")

    # Themes
    themes_dir = repo_path / "themes"
    total_themes = ingest_themes(conn, themes_dir)
    if total_themes:
        conn.commit()

    conn.close()

    print()
    print("=== Ingest Summary ===")
    print(f"  Companies ingested  : {total_companies}")
    print(f"  Supply chain entries: {total_supply_chain}")
    print(f"  Customer/supplier   : {total_customers}")
    print(f"  Theme associations  : {total_themes}")


def _ensure_research_tables(conn: sqlite3.Connection) -> None:
    """Create research tables if they don't already exist (mirrors db.py schema)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS research_companies (
            ticker       TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            sector       TEXT,
            industry     TEXT,
            market_cap   REAL,
            ev           REAL,
            description  TEXT,
            raw_markdown TEXT,
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS research_supply_chain (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT NOT NULL,
            direction   TEXT NOT NULL CHECK(direction IN ('upstream','downstream')),
            entity      TEXT NOT NULL,
            role_note   TEXT,
            FOREIGN KEY (ticker) REFERENCES research_companies(ticker)
        );

        CREATE TABLE IF NOT EXISTS research_customers (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker       TEXT NOT NULL,
            counterpart  TEXT NOT NULL,
            is_customer  INTEGER NOT NULL DEFAULT 1,
            note         TEXT,
            FOREIGN KEY (ticker) REFERENCES research_companies(ticker)
        );

        CREATE TABLE IF NOT EXISTS research_themes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker     TEXT NOT NULL,
            theme      TEXT NOT NULL,
            UNIQUE(ticker, theme),
            FOREIGN KEY (ticker) REFERENCES research_companies(ticker)
        );

        CREATE INDEX IF NOT EXISTS idx_research_industry ON research_companies(industry);
        CREATE INDEX IF NOT EXISTS idx_supply_chain_ticker ON research_supply_chain(ticker);
        CREATE INDEX IF NOT EXISTS idx_themes_theme ON research_themes(theme);
        CREATE INDEX IF NOT EXISTS idx_themes_ticker ON research_themes(ticker);
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest My-TW-Coverage markdown reports into the research_* tables."
    )
    parser.add_argument(
        "--repo-path",
        required=True,
        type=Path,
        help="Path to cloned My-TW-Coverage repository root.",
    )
    parser.add_argument(
        "--db-path",
        default=Path("data/ledger.db"),
        type=Path,
        help="Path to SQLite database file (default: data/ledger.db).",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    ingest(args.repo_path, args.db_path)
