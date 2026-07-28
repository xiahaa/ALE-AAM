"""Coordinate-grid helpers used by :mod:`ale_aam_maptool.scenario`."""
from __future__ import annotations


def utm_epsg(lon: float, lat: float) -> int:
    """Return the UTM EPSG code (326xx north / 327xx south) for a lon/lat point."""
    zone = int((lon + 180.0) // 6.0) + 1
    if zone > 60:
        zone = 60
    return 32600 + zone if lat >= 0 else 32700 + zone
