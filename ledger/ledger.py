"""Core StockLedger class."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date as Date
import bisect
from collections import defaultdict
from pathlib import Path
from typing import Generator

from .db import DEFAULT_DB, get_connection, init_db


class StockLedger:
    """
    Simple stock ledger backed by SQLite.

    Cash flow model
    ---------------
    - ``add_cash()``  : manual deposits (+) and withdrawals (-)
    - ``add_trade()`` : automatically adjusts the cash balance
        buy  → cash -= qty × price + commission
        sell → cash += qty × price − commission

    Price discovery order
    ---------------------
    1. ``prices`` table  (via ``add_price()``)
    2. Last recorded trade price for that symbol
    """

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else DEFAULT_DB
        with self._conn() as conn:
            init_db(conn)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = get_connection(self._db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Cash operations                                                      #
    # ------------------------------------------------------------------ #

    def add_cash(
        self,
        amount: float,
        date: str | Date,
        note: str = "",
    ) -> None:
        """
        Record a cash deposit (positive) or withdrawal (negative).

        Parameters
        ----------
        amount : float
            Positive = deposit, negative = withdrawal.
        date : str | date
            Transaction date, e.g. ``"2024-01-02"``.
        note : str
            Optional description.
        """
        if amount == 0:
            raise ValueError("amount must be non-zero")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO cash_entries (date, amount, note) VALUES (?,?,?)",
                (str(date), float(amount), note),
            )

    def void_cash(self, cash_id: int) -> None:
        """Soft-delete a cash entry by setting ``is_void = 1``.

        Raises ``ValueError`` if the entry does not exist or is already voided.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, is_void FROM cash_entries WHERE id = ?", (cash_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Cash entry {cash_id} not found")
            if row["is_void"]:
                raise ValueError(f"Cash entry {cash_id} is already voided")
            conn.execute("UPDATE cash_entries SET is_void = 1 WHERE id = ?", (cash_id,))

    def cash_balance(self, as_of: str | Date | None = None) -> float:
        """
        Return the cash balance as of a given date.

        Includes the cash impact of all trades recorded on or before that date.
        """
        as_of = str(as_of) if as_of else str(Date.today())
        with self._conn() as conn:
            manual = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM cash_entries WHERE date <= ? AND is_void = 0",
                (as_of,),
            ).fetchone()[0]

            trade_impact = conn.execute(
                """
                SELECT COALESCE(SUM(
                    CASE side
                        WHEN 'sell' THEN  qty * price - commission - tax
                        WHEN 'buy'  THEN -(qty * price + commission + tax)
                    END
                ), 0)
                FROM trades
                WHERE date <= ? AND is_void = 0
                """,
                (as_of,),
            ).fetchone()[0]

        return manual + trade_impact

    # ------------------------------------------------------------------ #
    # Trade operations                                                     #
    # ------------------------------------------------------------------ #

    def add_trade(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        date: str | Date,
        commission: float = 0.0,
        tax: float = 0.0,
        note: str = "",
    ) -> None:
        """
        Record a buy or sell trade.

        The cash balance is automatically adjusted.  A ``ValueError`` is
        raised if there is insufficient cash (buy) or insufficient shares (sell).

        Parameters
        ----------
        symbol : str
            Ticker symbol, e.g. ``"2330"`` or ``"AAPL"``.
        side : str
            ``"buy"`` or ``"sell"``.
        qty : float
            Number of shares (must be positive).
        price : float
            Trade price per share.
        date : str | date
            Trade date.
        commission : float
            Brokerage commission (default 0).
        tax : float
            Transaction tax (default 0). Included in cash cost/proceeds.
        note : str
            Optional description.
        """
        side = side.lower()
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        if qty <= 0:
            raise ValueError("qty must be positive")
        if price <= 0:
            raise ValueError("price must be positive")
        if commission < 0:
            raise ValueError("commission must be >= 0")
        if tax < 0:
            raise ValueError("tax must be >= 0")

        if side == "buy":
            cost = qty * price + commission + tax
            balance = self.cash_balance(as_of=date)
            if balance < cost:
                raise ValueError(
                    f"Insufficient cash: need {cost:,.2f} but have {balance:,.2f}"
                )
        else:
            held = self.position(symbol, as_of=date)
            if held < qty:
                raise ValueError(
                    f"Insufficient shares of {symbol}: need {qty} but hold {held}"
                )

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO trades (date, symbol, side, qty, price, commission, tax, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(date), symbol.upper(), side, float(qty),
                 float(price), float(commission), float(tax), note),
            )

    def position(self, symbol: str, as_of: str | Date | None = None) -> float:
        """Return the net share count held for *symbol* as of *as_of*."""
        as_of = str(as_of) if as_of else str(Date.today())
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(
                    CASE side WHEN 'buy' THEN qty ELSE -qty END
                ), 0)
                FROM trades
                WHERE symbol = ? AND date <= ? AND is_void = 0
                """,
                (symbol.upper(), as_of),
            ).fetchone()
        return row[0]

    def positions(self, as_of: str | Date | None = None) -> dict[str, float]:
        """Return all non-zero positions as of *as_of*."""
        as_of = str(as_of) if as_of else str(Date.today())
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT symbol,
                       SUM(CASE side WHEN 'buy' THEN qty ELSE -qty END) AS net_qty
                FROM trades
                WHERE date <= ? AND is_void = 0
                GROUP BY symbol
                HAVING net_qty > 0
                ORDER BY symbol
                """,
                (as_of,),
            ).fetchall()
        return {r["symbol"]: r["net_qty"] for r in rows}

    def trade_history(
        self,
        symbol: str | None = None,
        start: str | Date | None = None,
        end: str | Date | None = None,
        include_void: bool = False,
    ) -> list[dict]:
        """Return a list of trade records, optionally filtered.

        Voided trades are excluded by default; pass ``include_void=True``
        to include them (they carry ``is_void=1``).
        """
        clauses, params = [], []
        if not include_void:
            clauses.append("is_void = 0")
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol.upper())
        if start:
            clauses.append("date >= ?")
            params.append(str(start))
        if end:
            clauses.append("date <= ?")
            params.append(str(end))

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM trades {where} ORDER BY date, id",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def void_trade(self, trade_id: int) -> None:
        """Soft-delete a trade by setting ``is_void = 1``.

        The trade is excluded from all future balance, position,
        and P&L calculations.  Raises ``ValueError`` if the trade
        does not exist or is already voided.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, is_void FROM trades WHERE id = ?", (trade_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Trade {trade_id} not found")
            if row["is_void"]:
                raise ValueError(f"Trade {trade_id} is already voided")
            conn.execute("UPDATE trades SET is_void = 1 WHERE id = ?", (trade_id,))

    # ------------------------------------------------------------------ #
    # Price data                                                           #
    # ------------------------------------------------------------------ #

    def add_price(self, symbol: str, date: str | Date, close: float) -> None:
        """Insert or replace a daily closing price."""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO prices (date, symbol, close) VALUES (?,?,?)",
                (str(date), symbol.upper(), float(close)),
            )

    def last_price(self, symbol: str, as_of: str | Date | None = None) -> float | None:
        """
        Return the most recent close price on or before *as_of*.

        Looks up ``prices`` table first; falls back to the last trade price.
        Returns ``None`` if no price information is available.
        """
        as_of = str(as_of) if as_of else str(Date.today())
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT close FROM prices
                WHERE symbol = ? AND date <= ?
                ORDER BY date DESC LIMIT 1
                """,
                (symbol.upper(), as_of),
            ).fetchone()
            if row:
                return row[0]

            row = conn.execute(
                """
                SELECT price FROM trades
                WHERE symbol = ? AND date <= ? AND is_void = 0
                ORDER BY date DESC LIMIT 1
                """,
                (symbol.upper(), as_of),
            ).fetchone()
            return row[0] if row else None

    # ------------------------------------------------------------------ #
    # Portfolio snapshot                                                   #
    # ------------------------------------------------------------------ #

    def equity_snapshot(self, as_of: str | Date | None = None) -> dict:
        """
        Return a point-in-time portfolio snapshot.

        Returns a dict with keys:
            date, cash, market_value, total_equity, positions
        """
        as_of = str(as_of) if as_of else str(Date.today())
        cash = self.cash_balance(as_of=as_of)
        pos = self.positions(as_of=as_of)

        market_value = 0.0
        detail: dict[str, dict] = {}
        for sym, qty in pos.items():
            px = self.last_price(sym, as_of=as_of)
            mv = qty * px if px is not None else 0.0
            market_value += mv
            detail[sym] = {"qty": qty, "price": px, "market_value": mv}

        return {
            "date": as_of,
            "cash": cash,
            "market_value": market_value,
            "total_equity": cash + market_value,
            "positions": detail,
        }

    # ------------------------------------------------------------------ #
    # Cash flow statement                                                  #
    # ------------------------------------------------------------------ #

    def cash_flow(
        self,
        start: str | Date | None = None,
        end: str | Date | None = None,
        include_void: bool = False,
    ) -> list[dict]:
        """
        Return all cash movements (manual entries + trade impacts), sorted by date.

        Running ``balance`` is computed from non-voided entries only so it
        always matches ``cash_balance()``.  Voided cash entries are excluded
        by default; pass ``include_void=True`` to include them.

        Each entry contains:
            id, date, type, amount, symbol, note, balance, is_void
        """
        entries: list[dict] = []

        with self._conn() as conn:
            for r in conn.execute(
                "SELECT id, date, amount, note, is_void FROM cash_entries ORDER BY date, id"
            ).fetchall():
                entries.append({
                    "id": r["id"],
                    "date": r["date"],
                    "type": "deposit" if r["amount"] > 0 else "withdrawal",
                    "amount": float(r["amount"]),
                    "symbol": None,
                    "note": r["note"],
                    "is_void": bool(r["is_void"]),
                    "_sk": (r["date"], 0, r["id"]),
                })

            for r in conn.execute(
                "SELECT id, date, symbol, side, qty, price, commission, tax, note "
                "FROM trades WHERE is_void = 0 ORDER BY date, id"
            ).fetchall():
                if r["side"] == "buy":
                    amount = -(r["qty"] * r["price"] + r["commission"] + r["tax"])
                    type_ = "buy"
                else:
                    amount = r["qty"] * r["price"] - r["commission"] - r["tax"]
                    type_ = "sell"
                entries.append({
                    "id": None,
                    "date": r["date"],
                    "type": type_,
                    "amount": float(amount),
                    "symbol": r["symbol"],
                    "note": r["note"],
                    "is_void": False,
                    "_sk": (r["date"], 1, r["id"]),
                })

        entries.sort(key=lambda x: x["_sk"])

        # Running balance excludes voided entries (matches cash_balance())
        balance = 0.0
        for e in entries:
            if not e["is_void"]:
                balance += e["amount"]
            e["balance"] = round(balance, 2)
            del e["_sk"]

        # Filter out voided entries unless requested
        if not include_void:
            entries = [e for e in entries if not e["is_void"]]

        # Apply date filter after balance computation
        start_str = str(start) if start else None
        end_str = str(end) if end else None
        if start_str or end_str:
            entries = [
                e for e in entries
                if (not start_str or e["date"] >= start_str)
                and (not end_str or e["date"] <= end_str)
            ]

        return entries

    # ------------------------------------------------------------------ #
    # Position P&L (Weighted Average Cost)                                 #
    # ------------------------------------------------------------------ #

    def position_pnl(
        self,
        symbol: str,
        as_of: str | Date | None = None,
    ) -> dict:
        """
        Detailed P&L for *symbol* using the Weighted Average Cost method.

        Buy commission is included in the cost basis (per share).
        Sell commission is deducted from realized proceeds.

        Returns
        -------
        dict
            symbol, qty, avg_cost, realized_pnl, unrealized_pnl,
            last_price, price_source, market_value
        """
        as_of = str(as_of) if as_of else str(Date.today())

        with self._conn() as conn:
            rows = conn.execute(
                "SELECT side, qty, price, commission, tax FROM trades "
                "WHERE symbol = ? AND date <= ? AND is_void = 0 ORDER BY date, id",
                (symbol.upper(), as_of),
            ).fetchall()

        shares = 0.0
        avg_cost = 0.0      # per share, includes buy commission + tax
        realized = 0.0

        for t in rows:
            qty = t["qty"]
            price = t["price"]
            comm = t["commission"]
            tax = t["tax"]

            if t["side"] == "buy":
                cost_per_share = (qty * price + comm + tax) / qty
                avg_cost = (shares * avg_cost + qty * cost_per_share) / (shares + qty)
                shares += qty
            else:
                realized += (price - avg_cost) * qty - comm - tax
                shares -= qty

        px, source = self._last_price_with_source(symbol, as_of)
        unrealized = (
            round((px - avg_cost) * shares, 2)
            if (px is not None and shares > 0)
            else None
        )

        return {
            "symbol": symbol.upper(),
            "qty": shares,
            "avg_cost": round(avg_cost, 4) if shares > 0 else None,
            "realized_pnl": round(realized, 2),
            "unrealized_pnl": unrealized,
            "last_price": px,
            "price_source": source,
            "market_value": round(px * shares, 2) if (px is not None and shares > 0) else None,
        }

    def all_positions_pnl(
        self,
        as_of: str | Date | None = None,
        open_only: bool = True,
    ) -> list[dict]:
        """
        Return ``position_pnl`` for every symbol that has ever had a trade.

        Parameters
        ----------
        open_only : bool
            If ``True`` (default), only symbols with qty > 0 are returned.
        """
        as_of = str(as_of) if as_of else str(Date.today())

        with self._conn() as conn:
            symbols = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT symbol FROM trades "
                    "WHERE date <= ? AND is_void = 0 ORDER BY symbol",
                    (as_of,),
                ).fetchall()
            ]

        results = [self.position_pnl(sym, as_of=as_of) for sym in symbols]
        if open_only:
            results = [r for r in results if r["qty"] > 0]
        return results

    # ------------------------------------------------------------------ #
    # Daily equity & P&L                                                  #
    # ------------------------------------------------------------------ #

    def daily_equity(
        self,
        start: str | Date,
        end: str | Date,
        freq: str = "B",
    ) -> list[dict]:
        """
        Return one record per date in [start, end].

        Parameters
        ----------
        freq : str
            ``"D"`` = every calendar day, ``"B"`` = business days (Mon–Fri).

        Each record contains:
            date, cash, market_value, total_equity,
            external_cashflow, daily_change, daily_pnl,
            daily_return_pct, price_staleness_days, used_quote_date_map
        """
        import pandas as pd
        from pandas.tseries.offsets import BDay

        start_str = str(start)
        end_str   = str(end)

        dates = pd.date_range(start_str, end_str, freq=freq)
        end_ts = pd.Timestamp(end_str)
        if len(dates) == 0 or dates[-1] != end_ts:
            dates = dates.append(pd.DatetimeIndex([end_ts]))
        date_strs = [ts.date().isoformat() for ts in dates]

        # "yesterday" before the first record
        if freq == "B":
            prev_date = (pd.Timestamp(start_str) - BDay(1)).date().isoformat()
        else:
            prev_date = (
                pd.Timestamp(start_str) - pd.Timedelta(days=1)
            ).date().isoformat()

        # Pre-fetch external cashflows (cash_entries only, no trades)
        with self._conn() as conn:
            cf_rows = conn.execute(
                "SELECT date, SUM(amount) AS total FROM cash_entries "
                "WHERE date >= ? AND date <= ? AND is_void = 0 GROUP BY date",
                (prev_date, end_str),
            ).fetchall()
            # Pre-fetch all quote dates up to end
            q_rows = conn.execute(
                "SELECT symbol, date FROM prices WHERE date <= ? ORDER BY symbol, date",
                (end_str,),
            ).fetchall()

        cashflow_map: dict[str, float] = {r["date"]: float(r["total"]) for r in cf_rows}

        # {symbol: sorted list of quote dates}
        symbol_quotes: dict[str, list[str]] = defaultdict(list)
        for r in q_rows:
            symbol_quotes[r["symbol"]].append(r["date"])

        def _last_quote(sym: str, as_of: str) -> str | None:
            qdates = symbol_quotes.get(sym, [])
            if not qdates:
                return None
            i = bisect.bisect_right(qdates, as_of) - 1
            return qdates[i] if i >= 0 else None

        prev_snap = self.equity_snapshot(as_of=prev_date)
        prev_equity = prev_snap["total_equity"]

        records: list[dict] = []
        for date_str in date_strs:
            snap = self.equity_snapshot(as_of=date_str)
            total_equity = snap["total_equity"]
            external_cashflow = cashflow_map.get(date_str, 0.0)

            daily_change = total_equity - prev_equity
            daily_pnl    = daily_change - external_cashflow
            daily_return_pct = (
                round(daily_pnl / prev_equity * 100, 4)
                if prev_equity != 0 else None
            )

            # Price staleness
            from datetime import date as _Date
            as_of_d = _Date.fromisoformat(date_str)
            max_staleness: int | None = None
            quote_date_map: dict[str, str | None] = {}
            for sym in snap["positions"]:
                lq = _last_quote(sym, date_str)
                quote_date_map[sym] = lq
                if lq is not None:
                    staleness = (as_of_d - _Date.fromisoformat(lq)).days
                    max_staleness = (
                        staleness if max_staleness is None
                        else max(max_staleness, staleness)
                    )

            records.append({
                "date":                 date_str,
                "cash":                 snap["cash"],
                "market_value":         snap["market_value"],
                "total_equity":         total_equity,
                "external_cashflow":    round(external_cashflow, 2),
                "daily_change":         round(daily_change, 2),
                "daily_pnl":            round(daily_pnl, 2),
                "daily_return_pct":     daily_return_pct,
                "price_staleness_days": max_staleness,
                "used_quote_date_map":  quote_date_map,
            })
            prev_equity = total_equity

        return records

    # ------------------------------------------------------------------ #
    # Position detail (cost summary + WAC history)                        #
    # ------------------------------------------------------------------ #

    def position_detail(
        self,
        symbol: str,
        as_of: str | Date | None = None,
    ) -> dict:
        """
        Extended position detail: base P&L + cost_summary + running_wac + wac_series.
        """
        as_of = str(as_of) if as_of else str(Date.today())
        sym = symbol.upper()

        pnl = self.position_pnl(sym, as_of=as_of)

        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, date, side, qty, price, commission, tax, note FROM trades "
                "WHERE symbol = ? AND date <= ? AND is_void = 0 ORDER BY date, id",
                (sym, as_of),
            ).fetchall()
        trades = [dict(r) for r in rows]
        buys = [t for t in trades if t["side"] == "buy"]

        if buys:
            cost_summary = {
                "buy_count": len(buys),
                "buy_qty_total": sum(t["qty"] for t in buys),
                "buy_cost_total_including_fees": round(
                    sum(t["qty"] * t["price"] + t["commission"] + t["tax"] for t in buys), 2
                ),
                "min_buy_price": min(t["price"] for t in buys),
                "max_buy_price": max(t["price"] for t in buys),
                "first_buy_date": buys[0]["date"],
                "last_buy_date":  buys[-1]["date"],
            }
        else:
            cost_summary = None

        shares = 0.0
        avg_cost = 0.0
        running_wac: list[dict] = []
        wac_series: list[dict] = []

        for t in trades:
            qty   = t["qty"]
            price = t["price"]
            comm  = t["commission"]
            tax   = t["tax"]
            if t["side"] == "buy":
                cost_per_share = (qty * price + comm + tax) / qty
                avg_cost = (shares * avg_cost + qty * cost_per_share) / (shares + qty)
                shares += qty
            else:
                shares -= qty

            entry = {
                "trade_id":       t["id"],
                "date":           t["date"],
                "side":           t["side"],
                "qty":            qty,
                "price":          price,
                "commission":     comm,
                "tax":            tax,
                "qty_after":      round(shares, 6),
                "avg_cost_after": round(avg_cost, 4) if shares > 0 else None,
            }
            running_wac.append(entry)
            if shares > 0:
                wac_series.append({"date": t["date"], "avg_cost": round(avg_cost, 4)})

        px  = pnl.get("last_price")
        avg = pnl.get("avg_cost")
        pnl_pct = (
            round((px - avg) / avg * 100, 2)
            if (px and avg and pnl["qty"] > 0) else None
        )

        return {**pnl, "pnl_pct": pnl_pct, "cost_summary": cost_summary,
                "running_wac": running_wac, "wac_series": wac_series}

    # ------------------------------------------------------------------ #
    # Lot-level position detail (FIFO / LIFO / WAC)                       #
    # ------------------------------------------------------------------ #

    def lots_by_method(
        self,
        symbol: str,
        as_of: str | Date | None = None,
        method: str = "fifo",
    ) -> dict:
        """
        Return lot-level position detail.

        method : ``"fifo"`` | ``"lifo"`` | ``"wac"``
            FIFO / LIFO pairs sells to specific buy lots.
            WAC shows remaining lots (fifo-tracked qty) but uses WAC cost for P&L.
        """
        as_of  = str(as_of) if as_of else str(Date.today())
        sym    = symbol.upper()
        method = method.lower()
        if method not in ("fifo", "lifo", "wac"):
            raise ValueError(f"method must be fifo, lifo, or wac; got '{method}'")

        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, date, side, qty, price, commission, tax FROM trades "
                "WHERE symbol = ? AND date <= ? AND is_void = 0 ORDER BY date, id",
                (sym, as_of),
            ).fetchall()
        trades = [dict(r) for r in rows]

        open_lots: list[dict] = []
        realized_breakdown: list[dict] = []
        lot_counter = 0
        shares_wac  = 0.0
        avg_cost_wac = 0.0

        for t in trades:
            qty   = t["qty"]
            price = t["price"]
            comm  = t["commission"]
            tax   = t["tax"]

            if t["side"] == "buy":
                lot_counter += 1
                cost_per_share = (qty * price + comm + tax) / qty
                avg_cost_wac = (
                    (shares_wac * avg_cost_wac + qty * cost_per_share)
                    / (shares_wac + qty)
                )
                shares_wac += qty
                open_lots.append({
                    "lot_id":       lot_counter,
                    "buy_trade_id": t["id"],
                    "buy_date":     t["date"],
                    "qty_remaining": qty,
                    "buy_price":    price,
                    "commission":   comm,
                    "tax":          tax,
                    "cost_per_share": round(cost_per_share, 4),
                })
            else:  # sell
                shares_wac -= qty
                remaining   = qty
                allocations: list[dict] = []

                indices = (
                    list(range(len(open_lots) - 1, -1, -1))
                    if method == "lifo"
                    else list(range(len(open_lots)))
                )
                for i in indices:
                    if remaining <= 0:
                        break
                    lot     = open_lots[i]
                    consume = min(lot["qty_remaining"], remaining)
                    lot["qty_remaining"] -= consume
                    remaining -= consume
                    prop = consume / qty
                    net_proceeds      = consume * price - comm * prop - tax * prop
                    realized_pnl_piece = net_proceeds - consume * lot["cost_per_share"]
                    allocations.append({
                        "lot_id":            lot["lot_id"],
                        "qty":               consume,
                        "buy_price":         lot["buy_price"],
                        "cost_per_share":    lot["cost_per_share"],
                        "realized_pnl_piece": round(realized_pnl_piece, 2),
                    })

                open_lots = [lot for lot in open_lots if lot["qty_remaining"] > 0]

                if method != "wac":
                    realized_breakdown.append({
                        "sell_trade_id": t["id"],
                        "sell_date":     t["date"],
                        "sell_qty":      qty,
                        "sell_price":    price,
                        "commission":    comm,
                        "tax":           tax,
                        "allocations":   allocations,
                    })

        px, _ = self._last_price_with_source(sym, as_of)
        result_lots: list[dict] = []
        for lot in open_lots:
            qty_rem  = lot["qty_remaining"]
            cost_ps  = avg_cost_wac if method == "wac" and avg_cost_wac > 0 else lot["cost_per_share"]
            mv       = round(qty_rem * px, 2) if px is not None else None
            tot_cost = round(qty_rem * cost_ps, 2)
            unreal   = round(mv - tot_cost, 2) if mv is not None else None
            result_lots.append({
                "lot_id":         lot["lot_id"],
                "buy_trade_id":   lot["buy_trade_id"],
                "buy_date":       lot["buy_date"],
                "qty_remaining":  qty_rem,
                "buy_price":      lot["buy_price"],
                "commission":     lot["commission"],
                "tax":            lot["tax"],
                "cost_per_share": round(cost_ps, 4),
                "total_cost":     tot_cost,
                "market_price":   px,
                "market_value":   mv,
                "unrealized_pnl": unreal,
            })

        return {
            "symbol":            sym,
            "method":            method,
            "as_of":             as_of,
            "position_qty":      round(shares_wac, 6),
            "avg_cost_wac":      round(avg_cost_wac, 4) if shares_wac > 0 else None,
            "lots":              result_lots,
            "realized_breakdown": realized_breakdown,
        }

    # ------------------------------------------------------------------ #
    # Price with source annotation                                         #
    # ------------------------------------------------------------------ #

    def _last_price_with_source(
        self,
        symbol: str,
        as_of: str | Date | None = None,
    ) -> tuple[float | None, str | None]:
        """Return ``(price, source)``; source is ``'quote'`` or ``'trade_fallback'``."""
        as_of = str(as_of) if as_of else str(Date.today())

        with self._conn() as conn:
            row = conn.execute(
                "SELECT close FROM prices WHERE symbol = ? AND date <= ? "
                "ORDER BY date DESC LIMIT 1",
                (symbol.upper(), as_of),
            ).fetchone()
            if row:
                return row[0], "quote"

            row = conn.execute(
                "SELECT price FROM trades "
                "WHERE symbol = ? AND date <= ? AND is_void = 0 "
                "ORDER BY date DESC LIMIT 1",
                (symbol.upper(), as_of),
            ).fetchone()
            if row:
                return row[0], "trade_fallback"

        return None, None

    def last_price_with_source(
        self,
        symbol: str,
        as_of: str | Date | None = None,
    ) -> dict:
        """Public wrapper: returns ``{symbol, price, price_source}``."""
        price, source = self._last_price_with_source(symbol, as_of)
        return {
            "symbol": symbol.upper(),
            "price": price,
            "price_source": source,
        }
