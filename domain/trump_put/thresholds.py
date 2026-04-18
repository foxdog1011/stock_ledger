from __future__ import annotations

SP500_ELECTION_CLOSE = 5782.76

SP500_ZONES: list[tuple[float, float, str, int]] = [
    # (lower, upper, zone_name, component_score)
    (5783, 99999, "Above Election Day", 0),
    (5400, 5783,         "Media Pressure Zone", 20),
    (5200, 5400,         "Nibble Zone (BofA)", 40),
    (5000, 5200,         "Heavy Buy Zone", 65),
    (4800, 5000,         "Trump Put Activated (BofA)", 85),
    (0,    4800,         "Deep Crisis", 100),
]

TNX_ZONES: list[tuple[float, float, str, int]] = [
    (0,    3.5, "Low / Calm", 0),
    (3.5,  4.0, "Normal", 10),
    (4.0,  4.3, "Elevated", 30),
    (4.3,  4.5, "Warning", 55),
    (4.5,  5.0, "Danger (April 2025 trigger)", 80),
    (5.0, 20.0, "Bond Crisis", 100),
]

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


def classify(indicator: str, value: float) -> tuple[str, int]:
    zones = {
        "sp500":   SP500_ZONES,
        "tnx":     TNX_ZONES,
        "vix":     VIX_ZONES,
        "dxy":     DXY_ZONES,
        "approval": APPROVAL_ZONES,
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
    ]:
        result[key] = [
            {"lower": z[0], "upper": z[1], "zone": z[2], "score": z[3]}
            for z in zones
        ]
    return result
