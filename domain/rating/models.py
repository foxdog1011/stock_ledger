"""Investment rating domain constants."""

RATING_VALUES = frozenset({"strong_buy", "buy", "hold", "sell", "strong_sell"})

UPDATABLE_RATING_FIELDS = frozenset({
    "rating", "target_price", "stop_loss", "thesis",
    "time_horizon", "confidence",
})
