"""Low-level grid helpers: projection + rasterization primitives.

These are pure-ish utilities used by :mod:`silas_maptool.scenario`. The heavy
``rasterio``/``pyproj`` work lives there; this module keeps the small, reusable
pieces (UTM selection, dilation) dependency-light.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter


def utm_epsg(lon: float, lat: float) -> int:
    """Return the UTM EPSG code (326xx north / 327xx south) for a lon/lat point."""
    zone = int((lon + 180.0) // 6.0) + 1
    if zone > 60:
        zone = 60
    return 32600 + zone if lat >= 0 else 32700 + zone


def dilate(mask: np.ndarray, radius_cells: int) -> np.ndarray:
    """Square (Chebyshev) binary dilation using PIL MaxFilter (no scipy/cv2 needed).

    ``mask`` is a boolean array of shape (H, W), north-up. ``radius_cells`` is the
    dilation radius in grid cells.
    """
    radius_cells = int(radius_cells)
    if radius_cells <= 0:
        return mask.astype(bool, copy=True)
    size = 2 * radius_cells + 1
    img = Image.fromarray((mask.astype(np.uint8)) * 255)
    out = img.filter(ImageFilter.MaxFilter(size))
    return np.asarray(out) > 0
