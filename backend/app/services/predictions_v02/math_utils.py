def round2(v: float) -> float:
    return round(float(v), 2)


def cap(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))

