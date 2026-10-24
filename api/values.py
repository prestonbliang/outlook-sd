"""Tolerant source-value parsing; one malformed observation must not break an outlook."""
import math


def finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def coordinates(lat, lon):
    lat, lon = finite_number(lat), finite_number(lon)
    return (lat, lon) if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 else None
