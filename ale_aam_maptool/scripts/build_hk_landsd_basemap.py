"""Build scenario-local MBTiles from the official Hong Kong LandsD map API.

The source is the key-free WGS84 topographic XYZ service documented by LandsD.
Downloads are deliberately serial and rate-limited. Every output has a sibling
manifest that records source URLs, acquisition time, coverage, counts, and hashes.
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
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image

from ale_aam_maptool.scenario import Scenario


API_TEMPLATE = (
    "https://mapapi.geodata.gov.hk/gs/api/v1.0.0/xyz/"
    "basemap/WGS84/{z}/{x}/{y}.png"
)
API_DOCUMENTATION = "https://portal.csdi.gov.hk/csdi-webpage/apidoc/TopographicMapAPI"
DATASET_PAGE = "https://data.gov.hk/en-data/dataset/hk-landsd-openmap-development-hkms-digital-b1k"
TERMS_PAGE = "https://data.gov.hk/en/terms-and-conditions"
ATTRIBUTION = "Map from Lands Department, HKSAR Government"
MERCATOR_LIMIT = 85.05112878
MAX_TILE_BYTES = 5_000_000


def _tile_x(longitude: float, zoom: int) -> float:
    return (longitude + 180.0) / 360.0 * (1 << zoom)


def _tile_y(latitude: float, zoom: int) -> float:
    latitude = max(-MERCATOR_LIMIT, min(MERCATOR_LIMIT, latitude))
    radians = math.radians(latitude)
    return (1.0 - math.asinh(math.tan(radians)) / math.pi) / 2.0 * (1 << zoom)


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


def _transparent_tile() -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (256, 256), (0, 0, 0, 0)).save(
        output, format="PNG", optimize=True, compress_level=9
    )
    return output.getvalue()


EMPTY_TILE = _transparent_tile()


def _digest(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


class LandsDDownloader:
    """Serial, cached downloader with bounded retry and no credentials."""

    def __init__(self, cache_dir: Path, interval: float, timeout: float, retries: int):
        self.cache_dir = cache_dir
        self.interval = interval
        self.timeout = timeout
        self.retries = retries
        self.network_requests = 0
        self.cache_hits = 0
        self._last_request = 0.0

    def _cache_path(self, zoom: int, x: int, y: int) -> Path:
        return self.cache_dir / str(zoom) / str(x) / f"{y}.png"

    @staticmethod
    def _valid_png(payload: bytes) -> bool:
        return bool(payload) and len(payload) <= MAX_TILE_BYTES and payload.startswith(b"\x89PNG\r\n\x1a\n")

    def _wait(self) -> None:
        remaining = self.interval - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)

    def __call__(self, zoom: int, x: int, y: int) -> tuple[bytes, bool, bool]:
        cached = self._cache_path(zoom, x, y)
        if cached.is_file():
            payload = cached.read_bytes()
            if self._valid_png(payload):
                self.cache_hits += 1
                return payload, payload == EMPTY_TILE, False

        url = API_TEMPLATE.format(z=zoom, x=x, y=y)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            self._wait()
            request = Request(url, headers={
                "User-Agent": "ALE-AAM/0.2 offline-basemap-builder",
                "Accept": "image/png,image/*;q=0.8",
            })
            try:
                self.network_requests += 1
                with urlopen(request, timeout=self.timeout) as response:
                    self._last_request = time.monotonic()
                    status = int(getattr(response, "status", 200))
                    payload = response.read(MAX_TILE_BYTES + 1)
                if status == 204 or not payload:
                    payload, empty = EMPTY_TILE, True
                elif self._valid_png(payload):
                    empty = False
                else:
                    raise ValueError("upstream response is not a bounded PNG tile")
                cached.parent.mkdir(parents=True, exist_ok=True)
                temporary = cached.with_suffix(".tmp")
                temporary.write_bytes(payload)
                os.replace(temporary, cached)
                return payload, empty, True
            except HTTPError as exc:
                self._last_request = time.monotonic()
                if exc.code in {204, 404}:
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    cached.write_bytes(EMPTY_TILE)
                    return EMPTY_TILE, True, True
                last_error = exc
            except (URLError, TimeoutError, OSError, ValueError) as exc:
                self._last_request = time.monotonic()
                last_error = exc
            if attempt < self.retries:
                time.sleep(min(8.0, 2.0 ** attempt))
        raise RuntimeError(f"failed to download LandsD tile {zoom}/{x}/{y}: {last_error}")


def create_pack(
    scenario_path: Path,
    output: Path,
    minimum: int,
    maximum: int,
    padding: float,
    acquired_at: str,
    downloader=None,
) -> dict:
    """Create one atomic MBTiles file; downloader injection keeps tests offline."""
    if not (10 <= minimum <= maximum <= 20):
        raise ValueError("LandsD topographic zoom range must be between 10 and 20")
    if not (0 <= padding <= 1):
        raise ValueError("padding must be between 0 and 1")
    scenario_path = scenario_path.resolve()
    scenario = Scenario.load(scenario_path)
    bounds = _padded_bounds(scenario.lonlat_bounds(), padding)
    coordinates = list(_tile_coordinates(bounds, minimum, maximum))
    if not coordinates:
        raise ValueError("scenario bounds do not intersect any XYZ tiles")
    if downloader is None:
        raise ValueError("a LandsD downloader is required")

    output.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=".hk-landsd-", suffix=".mbtiles", dir=output.parent
    )
    os.close(handle)
    temporary = Path(temporary_name)
    empty_count = 0
    source_count = 0
    network_count = 0
    try:
        with closing(sqlite3.connect(temporary)) as connection:
            connection.executescript(
                "PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;"
                "CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT);"
                "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB);"
                "CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row);"
            )
            mission_name = str(scenario.task["mission"]["name"])
            mission_id = str(scenario.task["mission"]["id"])
            metadata = {
                "ale_aam_id": "hong-kong-landsd",
                "attribution": ATTRIBUTION,
                "bounds": ",".join(f"{value:.8f}" for value in bounds),
                "center": f"{(bounds[0] + bounds[2]) / 2:.8f},{(bounds[1] + bounds[3]) / 2:.8f},{maximum}",
                "description": "Official Hong Kong LandsD topographic map snapshot for offline ALE-AAM visualization",
                "format": "png",
                "maxzoom": str(maximum),
                "minzoom": str(minimum),
                "name": f"香港地政总署离线地形图 · {mission_name}",
                "type": "baselayer",
                "version": "1.0",
            }
            connection.executemany(
                "INSERT INTO metadata(name,value) VALUES (?,?)", sorted(metadata.items())
            )
            for position, (zoom, x, y) in enumerate(coordinates, start=1):
                payload, empty, used_network = downloader(zoom, x, y)
                if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError(f"tile {zoom}/{x}/{y} is not PNG")
                empty_count += int(empty)
                source_count += int(not empty)
                network_count += int(used_network)
                tms_y = (1 << zoom) - 1 - y
                connection.execute(
                    "INSERT INTO tiles VALUES (?,?,?,?)", (zoom, x, tms_y, payload)
                )
                if position % 250 == 0:
                    connection.commit()
                    print(
                        json.dumps({"progress": position, "total": len(coordinates), "scenario": mission_id}),
                        flush=True,
                    )
            connection.commit()
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()

    result = {
        "schema_version": "1.0",
        "kind": "hong-kong-landsd-topographic-snapshot",
        "pack": output.name,
        "sha256": _digest(output),
        "size_bytes": output.stat().st_size,
        "tile_count": len(coordinates),
        "source_tile_count": source_count,
        "empty_tile_count": empty_count,
        "network_tile_count": network_count,
        "min_zoom": minimum,
        "max_zoom": maximum,
        "bounds": [round(value, 8) for value in bounds],
        "acquisition_date_utc": acquired_at,
        "attribution": ATTRIBUTION,
        "source": {
            "api_template": API_TEMPLATE,
            "api_documentation": API_DOCUMENTATION,
            "dataset": DATASET_PAGE,
            "terms": TERMS_PAGE,
            "crs": "EPSG:3857 XYZ tiles requested through the LandsD WGS84 endpoint",
            "license": "DATA.GOV.HK Terms and Conditions",
        },
        "scenario_sources": [
            {"path": "task.json", "sha256": _digest(scenario_path / "task.json")},
            {"path": "dem.tif", "sha256": _digest(scenario_path / "dem.tif")},
        ],
        "generation": {
            "coordinate_order": "[longitude, latitude]",
            "padding_fraction": padding,
            "tile_order": "zoom, x, y ascending",
            "requests": "serial, rate-limited, cached, bounded retry",
            "request_interval_seconds": getattr(downloader, "interval", None),
            "empty_response_policy": "transparent PNG tile",
        },
    }
    manifest = output.with_suffix(".manifest.json")
    manifest_text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    handle, temporary_manifest_name = tempfile.mkstemp(
        prefix=".hk-landsd-", suffix=".manifest.json", dir=output.parent
    )
    os.close(handle)
    temporary_manifest = Path(temporary_manifest_name)
    try:
        temporary_manifest.write_text(manifest_text, encoding="utf-8")
        os.replace(temporary_manifest, manifest)
    finally:
        if temporary_manifest.exists():
            temporary_manifest.unlink()
    return {**result, "scenario": str(scenario_path), "output": str(output), "manifest": str(manifest)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", action="append", type=Path, required=True,
                        help="Scenario directory; repeat for multiple packs.")
    parser.add_argument("--output-name", default="hong_kong_landsd.mbtiles")
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/hk-landsd-tiles"))
    parser.add_argument("--min-zoom", type=int, default=12)
    parser.add_argument("--max-zoom", type=int, default=17)
    parser.add_argument("--padding", type=float, default=0.10)
    parser.add_argument("--request-interval", type=float, default=0.20,
                        help="Minimum delay between requests in seconds; do not set below 0.10.")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--acquired-at", default=None,
                        help="UTC ISO-8601 snapshot time; defaults to the current time.")
    args = parser.parse_args()
    if args.request_interval < 0.10:
        parser.error("--request-interval must be at least 0.10 seconds")
    if args.retries < 0 or args.retries > 8:
        parser.error("--retries must be between 0 and 8")
    if Path(args.output_name).name != args.output_name or not args.output_name.endswith(".mbtiles"):
        parser.error("--output-name must be a plain .mbtiles filename")
    acquired_at = args.acquired_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    downloader = LandsDDownloader(
        args.cache_dir.resolve(), args.request_interval, args.timeout, args.retries
    )
    packs = []
    for scenario_path in args.scenario:
        resolved = scenario_path.resolve()
        packs.append(create_pack(
            resolved,
            resolved / "basemaps" / args.output_name,
            args.min_zoom,
            args.max_zoom,
            args.padding,
            acquired_at,
            downloader,
        ))
    print(json.dumps({
        "ok": True,
        "packs": packs,
        "cache_hits": downloader.cache_hits,
        "network_requests": downloader.network_requests,
    }, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
