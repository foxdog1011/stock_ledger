from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


@router.get("/trump-put/report", summary="Trump Put proximity report")
def get_report(fmt: str = Query("json", enum=["json", "discord", "plain"])):
    from domain.trump_put import service, formatter

    report = service.generate_report()

    if fmt == "discord":
        return {"text": formatter.format_discord(report)}
    if fmt == "plain":
        return {"text": formatter.format_plain(report)}
    return formatter.to_json(report)


@router.get("/trump-put/thresholds", summary="Threshold definitions")
def get_thresholds():
    from domain.trump_put.thresholds import get_all_thresholds
    return get_all_thresholds()


@router.get("/trump-put/history", summary="Historical tariff & Iran events")
def get_history():
    from domain.trump_put.historical import EVENTS
    return [
        {
            "date": str(ev.date),
            "sp500": ev.sp500,
            "tnx": ev.tnx,
            "description": ev.description,
            "event_type": ev.event_type,
        }
        for ev in EVENTS
    ]


@router.get("/trump-put/chart-data", summary="Market history for charts")
def get_chart_data(period: str = Query("6mo")):
    from domain.trump_put import fetcher
    return {
        "sp500": fetcher.fetch_history("sp500", period),
        "tnx": fetcher.fetch_history("tnx", period),
        "vix": fetcher.fetch_history("vix", period),
        "dxy": fetcher.fetch_history("dxy", period),
    }


@router.get("/trump-put/backtest", summary="Historical backtest analytics")
def get_backtest():
    from domain.trump_put import backtest
    result = backtest.compute_backtest()
    return backtest.to_json(result)


@router.get("/trump-put/tariffs", summary="Tariff tracking timeline")
def get_tariffs(
    country: str | None = Query(None),
    status: str | None = Query(None),
):
    from domain.trump_put import tariffs
    return {
        "events": tariffs.load_tariffs(country=country, status=status),
        "summary": tariffs.get_summary(),
    }


@router.post("/trump-put/alert", summary="Manual Discord alert trigger")
def trigger_alert(key: str = Query(...)):
    jarvis_key = os.environ.get("JARVIS_KEY", "")
    if key != jarvis_key:
        raise HTTPException(403, "Invalid key")

    from domain.trump_put import service, discord_alert
    report = service.generate_report()
    ok = discord_alert.send_alert(report)
    return {"sent": ok, "score": report.composite_score}


@router.get("/trump-put/dashboard", summary="Trump Put Dashboard HTML")
def dashboard():
    from fastapi.responses import HTMLResponse
    from pathlib import Path
    html_path = Path(__file__).parent.parent / "static" / "trump_put_dashboard.html"
    if not html_path.exists():
        raise HTTPException(404, "Dashboard HTML not found")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))
