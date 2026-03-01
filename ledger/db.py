"""Database connection and schema initialisation."""
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).parent.parent / "data" / "ledger.db"


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cash_entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL,
            amount      REAL    NOT NULL,
            note        TEXT    DEFAULT '',
            is_void     INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL,
            symbol      TEXT    NOT NULL,
            side        TEXT    NOT NULL CHECK(side IN ('buy','sell')),
            qty         REAL    NOT NULL CHECK(qty > 0),
            price       REAL    NOT NULL CHECK(price > 0),
            commission  REAL    NOT NULL DEFAULT 0 CHECK(commission >= 0),
            tax         REAL    NOT NULL DEFAULT 0,
            note        TEXT    DEFAULT '',
            is_void     INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS prices (
            date    TEXT NOT NULL,
            symbol  TEXT NOT NULL,
            close   REAL NOT NULL CHECK(close > 0),
            PRIMARY KEY (date, symbol)
        );

        CREATE INDEX IF NOT EXISTS idx_cash_date  ON cash_entries(date);
        CREATE INDEX IF NOT EXISTS idx_trade_date ON trades(date);
        CREATE INDEX IF NOT EXISTS idx_trade_sym  ON trades(symbol, date);
        CREATE INDEX IF NOT EXISTS idx_price_sym  ON prices(symbol, date);
    """)
    conn.commit()

    # Migrations for databases created before these columns existed
    cash_cols = {row[1] for row in conn.execute("PRAGMA table_info(cash_entries)").fetchall()}
    if "is_void" not in cash_cols:
        conn.execute("ALTER TABLE cash_entries ADD COLUMN is_void INTEGER NOT NULL DEFAULT 0")
        conn.commit()

    trade_cols = {row[1] for row in conn.execute("PRAGMA table_info(trades)").fetchall()}
    if "is_void" not in trade_cols:
        conn.execute("ALTER TABLE trades ADD COLUMN is_void INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    if "tax" not in trade_cols:
        conn.execute("ALTER TABLE trades ADD COLUMN tax REAL NOT NULL DEFAULT 0")
        conn.commit()
