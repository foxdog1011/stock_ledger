from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    """Read a float from an environment variable with a fallback default."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "Invalid value for %s: %r, using default %s", name, raw, default
        )
        return default


SP500_ELECTION_CLOSE = _env_float("TRUMP_PUT_SP_ELECTION", 5783.0)
SP500_ACTIVATION = _env_float("TRUMP_PUT_SP_ACTIVATION", 5000.0)
TNX_DANGER = _env_float("TRUMP_PUT_10Y_DANGER", 4.5)


def _build_sp500_zones() -> list[tuple[float, float, str, int]]:
    election = SP500_ELECTION_CLOSE
    activation = SP500_ACTIVATION
    return [
        (election, 99999, "Above Election Day", 0),
        (election - 383, election, "Media Pressure Zone", 20),
        (election - 583, election - 383, "Nibble Zone (BofA)", 40),
        (activation, election - 583, "Heavy Buy Zone", 65),
        (activation - 200, activation, "Trump Put Activated (BofA)", 85),
        (0, activation - 200, "Deep Crisis", 100),
    ]


def _build_tnx_zones() -> list[tuple[float, float, str, int]]:
    danger = TNX_DANGER
    return [
        (0, 3.5, "Low / Calm", 0),
        (3.5, 4.0, "Normal", 10),
        (4.0, 4.3, "Elevated", 30),
        (4.3, danger, "Warning", 55),
        (danger, danger + 0.5, "Danger (April 2025 trigger)", 80),
        (danger + 0.5, 20.0, "Bond Crisis", 100),
    ]


SP500_ZONES: list[tuple[float, float, str, int]] = _build_sp500_zones()

TNX_ZONES: list[tuple[float, float, str, int]] = _build_tnx_zones()

VIX_ZONES: list[tuple[float, float, str, int]] = [
    (0,   15, "Calm", 0),
    (15,  20, "Normal", 10),
    (20,  30, "Elevated", 30),
    (30,  40, "High Fear", 55),
    (40,  50, "Extreme (2025 crisis level)", 80),
    (50, 200, "Panic (2020/2008 level)", 100),
]


DXY_ZONES: list[tuple[float, float, str, int]] = [
    (0,   98, "Weak Dollar", 0),
    (98, 101, "Normal", 10),
    (101, 104, "Strong", 30),
    (104, 107, "Very Strong", 55),
    (107, 110, "Extreme Strength", 80),
    (110, 200, "Dollar Crisis", 100),
]

APPROVAL_ZONES: list[tuple[float, float, str, int]] = [
    (50, 100, "Popular", 0),
    (45,  50, "Moderate", 20),
    (40,  45, "Weak", 45),
    (35,  40, "Unpopular", 70),
    (0,   35, "Deeply Unpopular", 100),
]

CREDIT_SPREAD_ZONES: list[tuple[float, float, str, int]] = [
    (0,    3.0, "Calm", 0),
    (3.0,  4.0, "Normal", 15),
    (4.0,  5.0, "Elevated", 35),
    (5.0,  6.0, "Stressed", 60),
    (6.0,  8.0, "High Yield Crisis", 80),
    (8.0, 100.0, "Credit Panic", 100),
]

TWEXB_ZONES: list[tuple[float, float, str, int]] = [
    (0,   105, "Weak Dollar", 0),
    (105, 110, "Normal", 10),
    (110, 115, "Strong", 30),
    (115, 120, "Very Strong", 55),
    (120, 125, "Extreme Strength", 80),
    (125, 300, "Dollar Crisis", 100),
]


def classify(indicator: str, value: float) -> tuple[str, int]:
    zones = {
        "sp500":        SP500_ZONES,
        "tnx":          TNX_ZONES,
        "vix":          VIX_ZONES,
        "dxy":          DXY_ZONES,
        "approval":     APPROVAL_ZONES,
        "credit_spread": CREDIT_SPREAD_ZONES,
        "twexb":        TWEXB_ZONES,
    }.get(indicator)

    if zones is None:
        return ("Unknown", 0)

    for lower, upper, name, score in zones:
        if lower <= value < upper:
            return (name, score)

    return (zones[-1][2], zones[-1][3])


def get_all_thresholds() -> dict[str, list[dict]]:
    result = {}
    for key, zones in [
        ("sp500", SP500_ZONES), ("tnx", TNX_ZONES), ("vix", VIX_ZONES),
        ("dxy", DXY_ZONES), ("approval", APPROVAL_ZONES),
        ("credit_spread", CREDIT_SPREAD_ZONES), ("twexb", TWEXB_ZONES),
    ]:
        result[key] = [
            {"lower": z[0], "upper": z[1], "zone": z[2], "score": z[3]}
            for z in zones
        ]
    return result
