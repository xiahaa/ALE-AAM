"""Create a tiny, deterministic offline MBTiles example from bundled GIS data.

The renderer uses only the scenario DEM and building footprints. It does not
contact TianDiTu, Mapbox, OpenStreetMap, or any other network service.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import sqlite3
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ale_aam_maptool.scenario import Scenario


TILE_SIZE = 256
MERCATOR_LIMIT = 85.05112878


def _tile_x(longitude: float, zoom: int) -> float:
    return (longitude + 180.0) / 360.0 * (1 << zoom)


def _tile_y(latitude: float, zoom: int) -> float:
    latitude = max(-MERCATOR_LIMIT, min(MERCATOR_LIMIT, latitude))
    radians = math.radians(latitude)
    return (1.0 - math.asinh(math.tan(radians)) / math.pi) / 2.0 * (1 << zoom)


def _longitude(global_x: np.ndarray, zoom: int) -> np.ndarray:
    return global_x / (1 << zoom) * 360.0 - 180.0


def _latitude(global_y: np.ndarray, zoom: int) -> np.ndarray:
    return np.degrees(np.arctan(np.sinh(math.pi * (1.0 - 2.0 * global_y / (1 << zoom)))))


def _padded_bounds(bounds: tuple[float, float, float, float], padding: float) -> tuple[float, ...]:
    west, south, east, north = bounds
    dx, dy = (east - west) * padding, (north - south) * padding
    return west - dx, south - dy, east + dx, north + dy


def _tile_coordinates(bounds: tuple[float, ...], minimum: int, maximum: int):
    west, south, east, north = bounds
    for zoom in range(minimum, maximum + 1):
        limit = (1 << zoom) - 1
        x_min = max(0, min(limit, math.floor(_tile_x(west, zoom))))
        x_max = max(0, min(limit, math.floor(_tile_x(east, zoom))))
        y_min = max(0, min(limit, math.floor(_tile_y(north, zoom))))
        y_max = max(0, min(limit, math.floor(_tile_y(south, zoom))))
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                yield zoom, x, y


def _rings(geometry: dict) -> list[list[list[float]]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if geometry_type == "Polygon":
        return [coordinates[0]] if coordinates else []
    if geometry_type == "MultiPolygon":
        return [polygon[0] for polygon in coordinates if polygon]
    return []


def _building_index(features: list[dict]) -> list[tuple[tuple[float, ...], list[list[float]], float]]:
    indexed = []
    for feature in features:
        properties = feature.get("properties") or {}
        try:
            height = max(0.0, float(properties.get("height_m") or 0.0))
        except (TypeError, ValueError):
            height = 0.0
        for ring in _rings(feature.get("geometry") or {}):
            if len(ring) < 3:
                continue
            xs = [float(point[0]) for point in ring]
            ys = [float(point[1]) for point in ring]
            indexed.append(((min(xs), min(ys), max(xs), max(ys)), ring, height))
    return indexed


def _tile_lonlat_bounds(zoom: int, x: int, y: int) -> tuple[float, ...]:
    west = float(_longitude(np.array(x), zoom))
    east = float(_longitude(np.array(x + 1), zoom))
    north = float(_latitude(np.array(y), zoom))
    south = float(_latitude(np.array(y + 1), zoom))
    return west, south, east, north


def _terrain(sc: Scenario, zoom: int, x: int, y: int) -> Image.Image:
    pixels = (np.arange(TILE_SIZE, dtype=np.float64) + 0.5) / TILE_SIZE
    longitudes = _longitude(x + pixels, zoom)
    latitudes = _latitude(y + pixels, zoom)
    lon_grid, lat_grid = np.meshgrid(longitudes, latitudes)
    metric_x, metric_y = sc.to_metric(lon_grid, lat_grid)
    columns = np.floor((metric_x - sc.grid.west) / sc.grid.resolution).astype(np.int64)
    rows = np.floor((sc.grid.north - metric_y) / sc.grid.resolution).astype(np.int64)
    valid = ((rows >= 0) & (rows < sc.grid.height) &
             (columns >= 0) & (columns < sc.grid.width))
    clipped_rows = np.clip(rows, 0, sc.grid.height - 1)
    clipped_columns = np.clip(columns, 0, sc.grid.width - 1)
    elevation = sc.dem[clipped_rows, clipped_columns] if sc.dem is not None else np.full(rows.shape, np.nan)
    valid &= np.isfinite(elevation)

    rgba = np.empty((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
    rgba[..., :] = (145, 184, 205, 255)  # water / outside the supplied DTM
    land = valid & (elevation > 0.5)
    low_land = valid & ~land
    rgba[low_land] = (171, 202, 214, 255)
    normalized = np.clip(elevation / 300.0, 0.0, 1.0)
    rgba[..., 0][land] = (205 - normalized[land] * 63).astype(np.uint8)
    rgba[..., 1][land] = (215 - normalized[land] * 44).astype(np.uint8)
    rgba[..., 2][land] = (192 - normalized[land] * 58).astype(np.uint8)
    rgba[..., 3] = 255
    return Image.fromarray(rgba, mode="RGBA")


def _tile_points(ring: list[list[float]], zoom: int, x: int, y: int) -> list[tuple[float, float]]:
    return [
        ((_tile_x(float(point[0]), zoom) - x) * TILE_SIZE,
         (_tile_y(float(point[1]), zoom) - y) * TILE_SIZE)
        for point in ring
    ]


def _render_tile(sc: Scenario, buildings, zoom: int, x: int, y: int) -> bytes:
    image = _terrain(sc, zoom, x, y)
    west, south, east, north = _tile_lonlat_bounds(zoom, x, y)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    drawing = ImageDraw.Draw(overlay)
    for (minx, miny, maxx, maxy), ring, height in buildings:
        if maxx < west or minx > east or maxy < south or miny > north:
            continue
        shade = int(max(74, 127 - min(height, 180.0) * 0.24))
        drawing.polygon(_tile_points(ring, zoom, x, y),
                        fill=(shade, shade + 5, shade + 10, 190),
                        outline=(63, 70, 79, 210))
    image = Image.alpha_composite(image, overlay).convert("RGB")
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True, compress_level=9)
    return output.getvalue()


def _digest(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def create_pack(scenario_path: Path, output: Path, minimum: int, maximum: int,
                padding: float) -> dict:
    if not (0 <= minimum <= maximum <= 22):
        raise ValueError("zoom range must be between 0 and 22")
    if not (0 <= padding <= 1):
        raise ValueError("padding must be between 0 and 1")
    sc = Scenario.load(scenario_path)
    bounds = _padded_bounds(sc.lonlat_bounds(), padding)
    buildings = _building_index(sc.vector_features["buildings"])
    coordinates = list(_tile_coordinates(bounds, minimum, maximum))
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=".example-basemap-", suffix=".mbtiles", dir=output.parent)
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        with sqlite3.connect(temporary) as connection:
            connection.executescript(
                "PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;"
                "CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT);"
                "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB);"
                "CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row);"
            )
            mission_name = str(sc.task["mission"]["name"])
            metadata = {
                "ale_aam_id": "example",
                "attribution": "ALE-AAM offline example · source: bundled Hong Kong LandsD scenario data",
                "bounds": ",".join(f"{value:.8f}" for value in bounds),
                "center": f"{(bounds[0] + bounds[2]) / 2:.8f},{(bounds[1] + bounds[3]) / 2:.8f},{maximum}",
                "description": "Deterministic offline visualization example rendered without online tiles",
                "format": "png",
                "maxzoom": str(maximum),
                "minzoom": str(minimum),
                "name": f"离线示例 · {mission_name}",
                "type": "baselayer",
                "version": "1.0",
            }
            connection.executemany("INSERT INTO metadata(name,value) VALUES (?,?)", sorted(metadata.items()))
            for zoom, x, y in coordinates:
                payload = _render_tile(sc, buildings, zoom, x, y)
                tms_y = (1 << zoom) - 1 - y
                connection.execute("INSERT INTO tiles VALUES (?,?,?,?)", (zoom, x, tms_y, payload))
            connection.commit()
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()

    source_files = []
    for name in ("task.json", "dem.tif", "buildings_3d.geojson"):
        source = scenario_path / name
        source_files.append({"path": name, "sha256": _digest(source)})
    result = {
        "schema_version": "1.0",
        "kind": "ale-aam-offline-basemap-example",
        "pack": output.name,
        "sha256": _digest(output),
        "size_bytes": output.stat().st_size,
        "tile_count": len(coordinates),
        "min_zoom": minimum,
        "max_zoom": maximum,
        "bounds": [round(value, 8) for value in bounds],
        "network_requests": 0,
        "sources": source_files,
    }
    manifest = output.with_suffix(".manifest.json")
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
    return {**result, "scenario": str(scenario_path), "output": str(output), "manifest": str(manifest)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", action="append", type=Path, required=True,
                        help="Scenario directory; repeat for multiple examples.")
    parser.add_argument("--min-zoom", type=int, default=12)
    parser.add_argument("--max-zoom", type=int, default=14)
    parser.add_argument("--padding", type=float, default=0.10)
    args = parser.parse_args()
    packs = []
    for scenario in args.scenario:
        resolved = scenario.resolve()
        packs.append(create_pack(resolved, resolved / "basemaps" / "example.mbtiles",
                                 args.min_zoom, args.max_zoom, args.padding))
    print(json.dumps({"ok": True, "packs": packs}, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
