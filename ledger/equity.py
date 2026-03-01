"""Equity curve calculation."""
from __future__ import annotations

from datetime import date as Date
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from .ledger import StockLedger


def equity_curve(
    ledger: "StockLedger",
    start: str | Date,
    end: str | Date,
    freq: str = "ME",
) -> pd.DataFrame:
    """
    Build a time-series equity curve between *start* and *end*.

    Parameters
    ----------
    ledger : StockLedger
    start  : str | date   e.g. ``"2024-01-01"``
    end    : str | date   e.g. ``"2024-12-31"``
    freq   : str
        Pandas offset alias.
        ``"D"``  = daily
        ``"W"``  = weekly (Sunday)
        ``"ME"`` = month-end  (default)
        ``"QE"`` = quarter-end

    Returns
    -------
    pd.DataFrame
        Columns: cash, market_value, total_equity, return_pct, cum_return_pct
        Index  : date
    """
    dates = pd.date_range(str(start), str(end), freq=freq)

    # Always include the exact end date
    end_ts = pd.Timestamp(str(end))
    if end_ts not in dates:
        dates = dates.append(pd.DatetimeIndex([end_ts]))

    rows = []
    for ts in dates:
        snap = ledger.equity_snapshot(as_of=ts.date().isoformat())
        rows.append(
            {
                "date": ts.date(),
                "cash": snap["cash"],
                "market_value": snap["market_value"],
                "total_equity": snap["total_equity"],
            }
        )

    df = pd.DataFrame(rows).set_index("date")
    df["return_pct"] = df["total_equity"].pct_change() * 100
    df["cum_return_pct"] = (
        df["total_equity"] / df["total_equity"].iloc[0] - 1
    ) * 100
    return df


def print_curve(df: pd.DataFrame, title: str = "Equity Curve") -> None:
    """Pretty-print the equity curve DataFrame to stdout."""
    try:
        from tabulate import tabulate

        formatted = df.copy()
        for col in ("cash", "market_value", "total_equity"):
            formatted[col] = formatted[col].apply(lambda v: f"{v:>14,.0f}")
        formatted["return_pct"] = formatted["return_pct"].apply(
            lambda v: f"{v:>+7.2f}%" if pd.notna(v) else "      —"
        )
        formatted["cum_return_pct"] = formatted["cum_return_pct"].apply(
            lambda v: f"{v:>+7.2f}%" if pd.notna(v) else "      —"
        )
        print(f"\n{'─'*70}")
        print(f"  {title}")
        print(f"{'─'*70}")
        print(tabulate(formatted, headers="keys", tablefmt="simple"))
        print(f"{'─'*70}\n")
    except ImportError:
        print(df.to_string())


def plot_curve(df: pd.DataFrame, output_path: str = "equity_curve.png") -> str:
    """Save a matplotlib equity curve chart to *output_path*."""
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                                    gridspec_kw={"height_ratios": [3, 1]})
    fig.suptitle("Portfolio Equity Curve", fontsize=14, fontweight="bold")

    dates = df.index.astype(str)

    # ── Upper panel: stacked area (cash + market value) ────────────────
    ax1.fill_between(dates, df["cash"], alpha=0.5, label="Cash", color="#4C9BE8")
    ax1.fill_between(dates, df["total_equity"], df["cash"],
                     alpha=0.5, label="Market Value", color="#F5A623")
    ax1.plot(dates, df["total_equity"], color="#2C3E50", linewidth=1.5,
             label="Total Equity")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda x, _: f"{x:,.0f}"
    ))
    ax1.set_ylabel("Portfolio Value (TWD)")
    ax1.legend(loc="upper left")
    ax1.grid(axis="y", linestyle="--", alpha=0.5)

    # ── Lower panel: cumulative return % ───────────────────────────────
    colors = ["#27AE60" if v >= 0 else "#E74C3C"
              for v in df["cum_return_pct"].fillna(0)]
    ax2.bar(dates, df["cum_return_pct"].fillna(0), color=colors, alpha=0.8)
    ax2.axhline(0, color="#2C3E50", linewidth=0.8)
    ax2.set_ylabel("Cum. Return (%)")
    ax2.grid(axis="y", linestyle="--", alpha=0.5)

    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    return output_path
