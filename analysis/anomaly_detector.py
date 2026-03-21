"""Time-series anomaly detection — two methods.

Method 1: Z-score (rolling 20-day window, no dependencies)
Method 2: PCA Autoencoder (reconstruction error with dynamic threshold, requires scikit-learn)
  - Trains a PCA compression (n_components=2) on all feature rows
  - Reconstructs each point and computes mean squared reconstruction error
  - Flags points where error > mean(RE) + ae_threshold * std(RE)
  - No contamination ratio — threshold is purely data-driven

Both methods return a list of AnomalyResult dicts so callers don't need
to care which algorithm was used.
"""
from __future__ import annotations

from typing import Optional

from .time_series import build_features

# ── Z-score detector ──────────────────────────────────────────────────────────

def zscore_detect(
    rows: list[dict],
    threshold: float = 2.5,
) -> list[dict]:
    """Detect anomalies using a rolling 20-day Z-score on close prices.

    A point is flagged when |zscore_20| > threshold.

    Args:
        rows: chronological list of {date, close, volume}.
        threshold: Z-score threshold (default 2.5 σ).

    Returns:
        List of anomaly dicts for flagged rows.
    """
    features = build_features(rows)
    anomalies = []

    for feat in features:
        z = feat.get("zscore_20")
        if z is None:
            continue
        if abs(z) > threshold:
            reasons = []
            if z > 0:
                reasons.append(f"收盤價高於20日均線 {z:.2f} 個標準差")
            else:
                reasons.append(f"收盤價低於20日均線 {abs(z):.2f} 個標準差")

            vol_r = feat.get("volume_ratio")
            if vol_r is not None and vol_r > 2.0:
                reasons.append(f"成交量異常放大 ({vol_r:.1f}x 均量)")
            elif vol_r is not None and vol_r < 0.3:
                reasons.append(f"成交量異常萎縮 ({vol_r:.2f}x 均量)")

            anomalies.append({
                "date": feat["date"],
                "close": feat["close"],
                "volume": feat["volume"],
                "zscore": round(z, 3),
                "volume_ratio": vol_r,
                "price_change_pct": feat["price_change_pct"],
                "method": "zscore",
                "reason": "；".join(reasons),
                "severity": "high" if abs(z) > 3.5 else "medium",
            })

    return sorted(anomalies, key=lambda x: x["date"], reverse=True)


# ── PCA Autoencoder detector ──────────────────────────────────────────────────

def autoencoder_detect(
    rows: list[dict],
    ae_threshold: float = 2.5,
) -> list[dict]:
    """Detect anomalies using PCA reconstruction error (linear autoencoder).

    Compresses features to 2 principal components and reconstructs back.
    A point is flagged when its reconstruction error exceeds
    mean(RE) + ae_threshold * std(RE) — a purely data-driven threshold
    with no fixed contamination ratio.

    Requires scikit-learn. Gracefully returns [] if not installed.

    Args:
        rows: chronological list of {date, close, volume}.
        ae_threshold: how many standard deviations above mean error to flag
                      (default 2.5 — roughly ~1% flag rate on normal data).

    Returns:
        List of anomaly dicts for flagged rows.
    """
    try:
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler
        import numpy as np
    except ImportError:
        return []

    features = build_features(rows)

    # Only use rows where rolling features are fully computed
    valid = [
        f for f in features
        if f.get("zscore_20") is not None
    ]

    if len(valid) < 20:
        return []

    X = np.array([
        [
            f["close"],
            f["volume_ratio"] if f.get("volume_ratio") is not None else 0.0,
            f["price_change_pct"],
            f.get("volatility_5") or 0.0,
            f.get("zscore_20") or 0.0,
            f.get("bb_pct") if f.get("bb_pct") is not None else 0.5,
        ]
        for f in valid
    ])

    # Standardise features (required for PCA to work correctly)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # PCA encode + decode = linear autoencoder
    n_components = min(2, X_scaled.shape[1] - 1)
    pca = PCA(n_components=n_components, random_state=42)
    X_reduced = pca.fit_transform(X_scaled)
    X_reconstructed = pca.inverse_transform(X_reduced)

    # Per-point mean squared reconstruction error
    reconstruction_errors = np.mean((X_scaled - X_reconstructed) ** 2, axis=1)

    mean_e = reconstruction_errors.mean()
    std_e = reconstruction_errors.std()
    threshold = mean_e + ae_threshold * std_e
    high_threshold = mean_e + (ae_threshold + 1.0) * std_e

    anomalies = []
    for feat, re_val in zip(valid, reconstruction_errors):
        if re_val <= threshold:
            continue

        vol_r = feat.get("volume_ratio")
        pct = feat["price_change_pct"]
        z = feat.get("zscore_20") or 0.0

        reasons = []
        if abs(z) > 2.0:
            direction = "上漲" if z > 0 else "下跌"
            reasons.append(f"價格{direction}異常 (Z={z:.2f})")
        if vol_r and vol_r > 2.0:
            reasons.append(f"成交量爆量 ({vol_r:.1f}x)")
        elif vol_r and vol_r < 0.3:
            reasons.append(f"成交量萎縮 ({vol_r:.2f}x)")
        if abs(pct) > 5:
            reasons.append(f"單日漲跌 {pct:+.1f}%")
        if not reasons:
            reasons.append(f"重建誤差異常 (RE={re_val:.4f}，閾值={threshold:.4f})")

        # Normalize reconstruction error to 0-1 anomaly score
        anomaly_score = round(
            min(1.0, (re_val - threshold) / max(std_e, 1e-9) / 2.0 + 0.5),
            3,
        )

        anomalies.append({
            "date": feat["date"],
            "close": feat["close"],
            "volume": feat["volume"],
            "zscore": round(z, 3),
            "volume_ratio": vol_r,
            "price_change_pct": pct,
            "anomaly_score": anomaly_score,
            "reconstruction_error": round(float(re_val), 6),
            "method": "autoencoder",
            "reason": "；".join(reasons),
            "severity": "high" if re_val > high_threshold else "medium",
        })

    return sorted(anomalies, key=lambda x: x["date"], reverse=True)


# ── Combined detector ─────────────────────────────────────────────────────────

def detect_anomalies(
    rows: list[dict],
    method: str = "both",
    zscore_threshold: float = 2.5,
    ae_threshold: float = 2.5,
    lookback: int = 60,
) -> dict:
    """Run anomaly detection and return a unified report.

    Args:
        rows: chronological {date, close, volume} list.
        method: "zscore" | "autoencoder" | "both"
        zscore_threshold: Z-score cutoff for method 1.
        ae_threshold: standard deviations above mean reconstruction error
                      for PCA Autoencoder (default 2.5, data-driven).
        lookback: how many recent rows to include in the result.

    Returns:
        dict with keys:
          - zscore_anomalies: list (empty if method != zscore/both)
          - ae_anomalies: list of PCA autoencoder anomalies
          - summary: human-readable summary string
          - latest_features: feature dict for the most recent row
          - sklearn_available: bool
    """
    sklearn_available = _check_sklearn()

    # Run detectors
    zs_results: list[dict] = []
    ae_results: list[dict] = []

    if method in ("zscore", "both"):
        zs_results = zscore_detect(rows, threshold=zscore_threshold)

    if method in ("autoencoder", "both") and sklearn_available:
        ae_results = autoencoder_detect(rows, ae_threshold=ae_threshold)

    # Latest feature snapshot (most recent row)
    features = build_features(rows)
    latest = features[-1] if features else {}

    # Build summary
    recent_zs = [a for a in zs_results if _within_days(a["date"], rows, lookback)]
    recent_ae = [a for a in ae_results if _within_days(a["date"], rows, lookback)]

    summary_parts = []
    if recent_zs:
        latest_zs = recent_zs[0]
        summary_parts.append(
            f"Z-score 偵測到 {len(recent_zs)} 個異常點，"
            f"最近一次 {latest_zs['date']}（Z={latest_zs['zscore']:+.2f}，{latest_zs['reason']}）"
        )
    else:
        summary_parts.append("Z-score 分析：近期無統計顯著異常")

    if sklearn_available:
        if recent_ae:
            latest_ae = recent_ae[0]
            summary_parts.append(
                f"Autoencoder 偵測到 {len(recent_ae)} 個重建誤差異常點，"
                f"最近一次 {latest_ae['date']}（{latest_ae['reason']}）"
            )
        else:
            summary_parts.append("Autoencoder：近期重建誤差均在正常範圍內")
    else:
        summary_parts.append("Autoencoder：sklearn 未安裝，僅使用 Z-score")

    # Latest status
    z_now = latest.get("zscore_20")
    if z_now is not None:
        summary_parts.append(
            f"當前 Z-score {z_now:+.2f}，"
            f"20日均線 {latest.get('ma20', 'N/A')}"
        )

    return {
        "zscore_anomalies": zs_results,
        "ae_anomalies": ae_results,
        "summary": "；".join(summary_parts),
        "latest_features": latest,
        "sklearn_available": sklearn_available,
    }


def _check_sklearn() -> bool:
    try:
        import sklearn  # noqa: F401
        return True
    except ImportError:
        return False


def _within_days(date_str: str, rows: list[dict], n: int) -> bool:
    """Check if date_str is within the last n rows."""
    if not rows:
        return False
    cutoff_idx = max(0, len(rows) - n)
    cutoff_date = rows[cutoff_idx]["date"]
    return date_str >= cutoff_date
