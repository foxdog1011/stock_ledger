from __future__ import annotations

from .models import TrumpPutReport


def _gauge(score: int) -> str:
    filled = score // 10
    empty = 10 - filled
    bar = "\u2588" * filled + "\u2591" * empty
    return f"[{bar}] {score}/100"


def _fmt_value(reading) -> str:
    if reading.symbol == "sp500":
        return f"{reading.value:,.2f}"
    if reading.symbol == "tnx":
        return f"{reading.value:.3f}%"
    if reading.symbol == "approval":
        return f"{reading.value:.1f}%"
    return f"{reading.value:.2f}"


def _zone_emoji(score: int) -> str:
    if score <= 20:
        return "\U0001f7e2"  # green circle
    if score <= 40:
        return "\U0001f7e1"  # yellow circle
    if score <= 60:
        return "\U0001f7e0"  # orange circle
    return "\U0001f534"  # red circle


def format_discord(report: TrumpPutReport) -> str:
    lines: list[str] = []
    ts = report.timestamp.strftime("%Y-%m-%d %H:%M")
    lines.append(f"## Trump Put Tracker \u2014 {ts}")
    lines.append("")

    lines.append(f"**Composite Score: {_gauge(report.composite_score)} \u2014 {report.composite_label}**")
    lines.append("")

    lines.append("| Indicator | Value | Zone | Score |")
    lines.append("|-----------|-------|------|-------|")

    for reading in [report.sp500, report.tnx, report.vix, report.dxy, report.approval]:
        if reading is None:
            continue
        emoji = _zone_emoji(reading.score)
        val = _fmt_value(reading)
        lines.append(
            f"| {emoji} {reading.name} | {val} | {reading.zone} | {reading.score} |"
        )

    lines.append("")

    lines.append("**Key Thresholds:**")
    lines.append("```")
    lines.append("S&P 500:  5,783 (election) > 5,400 (nibble) > 5,200 (buy) > 5,000 (PUT)")
    lines.append("10Y Yield: 4.5% = danger trigger (April 2025 actual)")
    lines.append("VIX:       30 = fear | 45 = extreme | 50+ = panic")
    lines.append("DXY:       104 = strong | 107 = extreme strength")
    lines.append("```")

    lines.append("")
    lines.append(f"**Analysis:** {report.narrative}")

    if report.nearby_events:
        lines.append("")
        lines.append("**Historical Context:**")
        for ev in report.nearby_events[:4]:
            prefix = {
                "reversal": "\u21A9\uFE0F",
                "escalation": "\u26A0\uFE0F",
                "marker": "\u2022",
            }.get(ev.event_type, "\u2022")
            sp = f"S&P {ev.sp500:,.0f}" if ev.sp500 else ""
            tnx_s = f" | 10Y {ev.tnx:.2f}%" if ev.tnx else ""
            lines.append(f"{prefix} {ev.date} {sp}{tnx_s} \u2014 {ev.description}")

    lines.append("")
    lines.append(
        "*Data: Yahoo Finance. Not investment advice. "
        "Thresholds based on BofA/Evercore research (April 2025).*"
    )

    text = "\n".join(lines)
    if len(text) > 1950:
        text = text[:1947] + "..."
    return text


def format_plain(report: TrumpPutReport) -> str:
    lines: list[str] = []
    ts = report.timestamp.strftime("%Y-%m-%d %H:%M")
    lines.append(f"=== Trump Put Tracker -- {ts} ===")
    lines.append("")
    lines.append(f"Composite Score: {report.composite_score}/100 ({report.composite_label})")
    lines.append("")

    for reading in [report.sp500, report.tnx, report.vix, report.dxy, report.approval]:
        if reading is None:
            continue
        val = _fmt_value(reading)
        lines.append(f"  {reading.name:15s}  {val:>12s}  [{reading.zone}]  score={reading.score}")

    lines.append("")
    lines.append(f"Analysis: {report.narrative}")
    lines.append("")

    if report.nearby_events:
        lines.append("Historical Context:")
        for ev in report.nearby_events[:5]:
            sp = f"S&P {ev.sp500:,.0f}" if ev.sp500 else ""
            lines.append(f"  {ev.date}  {ev.event_type:11s}  {sp:>12s}  {ev.description}")

    return "\n".join(lines)


def to_json(report: TrumpPutReport) -> dict:
    def _reading(r: object | None) -> dict | None:
        if r is None:
            return None
        return {
            "symbol": r.symbol,
            "name": r.name,
            "value": r.value,
            "as_of": r.as_of,
            "zone": r.zone,
            "score": r.score,
        }

    return {
        "timestamp": report.timestamp.isoformat(),
        "composite_score": report.composite_score,
        "composite_label": report.composite_label,
        "narrative": report.narrative,
        "indicators": {
            "sp500": _reading(report.sp500),
            "tnx": _reading(report.tnx),
            "vix": _reading(report.vix),
            "dxy": _reading(report.dxy),
            "approval": _reading(report.approval),
        },
        "nearby_events": [
            {
                "date": str(ev.date),
                "sp500": ev.sp500,
                "tnx": ev.tnx,
                "description": ev.description,
                "event_type": ev.event_type,
            }
            for ev in report.nearby_events
        ],
        "thresholds": report.thresholds,
        "backtest": report.backtest,
    }
