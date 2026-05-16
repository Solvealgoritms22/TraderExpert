from __future__ import annotations

from statistics import mean, pstdev


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return default if not b else a / b


def sma(values: list[float], period: int) -> float:
    if len(values) < period:
        return mean(values) if values else 0.0
    return mean(values[-period:])


def ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append((value * alpha) + (out[-1] * (1 - alpha)))
    return out


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    gains = []
    losses = []
    for prev, curr in zip(values[-period - 1 : -1], values[-period:]):
        delta = curr - prev
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))
    avg_gain = mean(gains) if gains else 0
    avg_loss = mean(losses) if losses else 0
    if avg_loss == 0:
        return 100.0 if avg_gain else 50.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(bars: list[dict], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    ranges = []
    for prev, curr in zip(bars[-period - 1 : -1], bars[-period:]):
        high = float(curr["high"])
        low = float(curr["low"])
        prev_close = float(prev["close"])
        ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return mean(ranges) if ranges else 0.0


def linear_slope(values: list[float], period: int = 20) -> float:
    sample = values[-period:] if len(values) >= period else values
    if len(sample) < 2:
        return 0.0
    xs = list(range(len(sample)))
    x_mean = mean(xs)
    y_mean = mean(sample)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, sample))
    denominator = sum((x - x_mean) ** 2 for x in xs)
    return _safe_div(numerator, denominator)


def compute_features(bars: list[dict]) -> dict:
    closes = [float(bar["close"]) for bar in bars]
    highs = [float(bar["high"]) for bar in bars]
    lows = [float(bar["low"]) for bar in bars]
    volumes = [float(bar.get("tick_volume") or 0) for bar in bars]
    if len(closes) < 60:
        raise ValueError("Se requieren al menos 60 velas para calcular indicadores.")

    close = closes[-1]
    returns = [_safe_div(curr - prev, prev) for prev, curr in zip(closes[:-1], closes[1:]) if prev]
    recent_returns = returns[-20:]
    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    macd_line = (ema12[-1] - ema26[-1]) if ema12 and ema26 else 0.0
    signal_line = ema_series([a - b for a, b in zip(ema12[-len(ema26) :], ema26)], 9)
    macd_signal = signal_line[-1] if signal_line else 0.0
    atr_value = atr(bars, 14)
    volatility = pstdev(recent_returns) if len(recent_returns) > 1 else 0.0
    slope = linear_slope(closes, 24)
    slope_pct = _safe_div(slope, close)
    support = min(lows[-40:])
    resistance = max(highs[-40:])
    range_position = _safe_div(close - support, resistance - support, 0.5)

    score = 0.0
    score += 1.0 if close > sma(closes, 20) else -1.0
    score += 1.0 if sma(closes, 20) > sma(closes, 50) else -1.0
    score += 0.75 if macd_line > macd_signal else -0.75
    score += 0.75 if slope_pct > 0 else -0.75
    rsi_value = rsi(closes, 14)
    if rsi_value > 70:
        score -= 0.5
    elif rsi_value < 30:
        score += 0.5

    abs_score = abs(score)
    local_direction = "WAIT"
    if abs_score >= 2.4:
        local_direction = "UP" if score > 0 else "DOWN"
    local_confidence = min(0.86, 0.50 + (abs_score / 7.0))
    if volatility > 0.006:
        local_confidence -= 0.08
    if range_position > 0.92 and local_direction == "UP":
        local_confidence -= 0.08
    if range_position < 0.08 and local_direction == "DOWN":
        local_confidence -= 0.08

    return {
        "close": close,
        "sma_20": sma(closes, 20),
        "sma_50": sma(closes, 50),
        "rsi_14": round(rsi_value, 2),
        "macd": round(macd_line, 8),
        "macd_signal": round(macd_signal, 8),
        "atr_14": round(atr_value, 8),
        "volatility_20": round(volatility, 8),
        "slope_24_pct": round(slope_pct, 8),
        "support_40": support,
        "resistance_40": resistance,
        "range_position": round(range_position, 4),
        "tick_volume_avg_20": mean(volumes[-20:]) if volumes else 0.0,
        "local_direction": local_direction,
        "local_confidence": round(max(0.0, min(1.0, local_confidence)), 3),
        "local_score": round(score, 3),
    }
