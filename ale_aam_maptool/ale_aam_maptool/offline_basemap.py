"""Read scenario-local MBTiles archives without exposing arbitrary paths.

Only ``*.mbtiles`` files directly inside ``SCENARIO/basemaps`` are discovered.
The browser receives a provider id and metadata; the absolute archive path never
leaves the server process.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote


_ID_PATTERN = re.compile(r"[^a-z0-9]+")
_FORMATS = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
_MAX_TILE_BYTES = 5_000_000


class OfflineBasemapError(RuntimeError):
    """The archive is malformed or does not contain a requested tile."""


def _connection(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(path.resolve().as_posix(), safe='/:')}?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True, timeout=2)


def _metadata(connection: sqlite3.Connection) -> dict[str, str]:
    try:
        return {str(name): str(value) for name, value in connection.execute(
            "SELECT name, value FROM metadata"
        )}
    except sqlite3.Error as exc:
        raise OfflineBasemapError("MBTiles metadata table is missing or invalid") from exc


def _integer(metadata: dict[str, str], key: str, fallback: int) -> int:
    try:
        return int(metadata.get(key, fallback))
    except (TypeError, ValueError) as exc:
        raise OfflineBasemapError(f"MBTiles {key} metadata must be an integer") from exc


def _bounds(value: str | None) -> list[float] | None:
    if not value:
        return None
    try:
        result = [round(float(item), 8) for item in value.split(",")]
    except ValueError as exc:
        raise OfflineBasemapError("MBTiles bounds metadata is invalid") from exc
    if len(result) != 4:
        raise OfflineBasemapError("MBTiles bounds metadata must contain west,south,east,north")
    west, south, east, north = result
    if not (-180 <= west < east <= 180 and -85.05112878 <= south < north <= 85.05112878):
        raise OfflineBasemapError("MBTiles bounds metadata is outside Web Mercator limits")
    return result


def inspect_pack(path: str | Path, *, include_sha256: bool = False) -> dict:
    """Validate one MBTiles file and return safe, JSON-serializable metadata."""
    archive = Path(path).resolve()
    if not archive.is_file() or archive.suffix.lower() != ".mbtiles":
        raise OfflineBasemapError("offline basemap must be an existing .mbtiles file")
    try:
        with _connection(archive) as connection:
            metadata = _metadata(connection)
            try:
                actual_minimum, actual_maximum, count = connection.execute(
                    "SELECT MIN(zoom_level), MAX(zoom_level), COUNT(*) FROM tiles"
                ).fetchone()
            except sqlite3.Error as exc:
                raise OfflineBasemapError("MBTiles tiles table is missing or invalid") from exc
    except OfflineBasemapError:
        raise
    except sqlite3.Error as exc:
        raise OfflineBasemapError("offline basemap could not be opened") from exc

    if not count or actual_minimum is None or actual_maximum is None:
        raise OfflineBasemapError("offline basemap contains no tiles")
    minimum = _integer(metadata, "minzoom", int(actual_minimum))
    maximum = _integer(metadata, "maxzoom", int(actual_maximum))
    if not (0 <= minimum <= maximum <= 22):
        raise OfflineBasemapError("offline basemap zoom range must be between 0 and 22")
    if minimum != int(actual_minimum) or maximum != int(actual_maximum):
        raise OfflineBasemapError("MBTiles zoom metadata does not match the stored tiles")
    tile_format = metadata.get("format", "png").lower()
    if tile_format not in _FORMATS:
        raise OfflineBasemapError("offline basemap format must be png, jpg, jpeg, or webp")

    raw_id = metadata.get("ale_aam_id", archive.stem).strip().lower()
    slug = _ID_PATTERN.sub("-", raw_id).strip("-") or "pack"
    result = {
        "id": f"offline-{slug}",
        "name": metadata.get("name", archive.stem),
        "online": False,
        "available": True,
        "attribution": metadata.get("attribution", "ALE-AAM offline basemap"),
        "min_zoom": minimum,
        "max_zoom": maximum,
        "tile_count": int(count),
        "size_bytes": archive.stat().st_size,
        "bounds": _bounds(metadata.get("bounds")),
        "format": tile_format,
    }
    if include_sha256:
        digest = hashlib.sha256()
        with archive.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        result["sha256"] = digest.hexdigest()
    return result


@lru_cache(maxsize=16)
def _discover(resolved_scenario: str) -> tuple[dict, ...]:
    directory = Path(resolved_scenario) / "basemaps"
    if not directory.is_dir():
        return ()
    resolved_directory = directory.resolve()
    packs: list[dict] = []
    used: set[str] = set()
    for archive in sorted(directory.glob("*.mbtiles"), key=lambda item: item.name.lower()):
        if archive.is_symlink() or archive.resolve().parent != resolved_directory:
            continue
        try:
            summary = inspect_pack(archive)
        except OfflineBasemapError:
            continue
        base_id = summary["id"]
        suffix = 2
        while summary["id"] in used:
            summary["id"] = f"{base_id}-{suffix}"
            suffix += 1
        used.add(summary["id"])
        summary["_path"] = str(archive.resolve())
        packs.append(summary)
    return tuple(packs)


def discover_packs(scenario_path: str | Path | None) -> list[dict]:
    if scenario_path is None:
        return []
    return [dict(item) for item in _discover(str(Path(scenario_path).resolve()))]


def clear_discovery_cache() -> None:
    _discover.cache_clear()


def public_pack(pack: dict) -> dict:
    return {key: value for key, value in pack.items() if not key.startswith("_")}


def read_tile(pack: dict, z: int, x: int, y: int) -> tuple[bytes, str]:
    if not (int(pack["min_zoom"]) <= z <= int(pack["max_zoom"])):
        raise OfflineBasemapError("tile is outside the offline basemap zoom range")
    tile_row = (1 << z) - 1 - y  # MBTiles stores TMS rows; HTTP uses XYZ rows.
    try:
        with _connection(Path(pack["_path"])) as connection:
            row = connection.execute(
                "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                (z, x, tile_row),
            ).fetchone()
    except sqlite3.Error as exc:
        raise OfflineBasemapError("offline basemap tile could not be read") from exc
    if row is None:
        raise OfflineBasemapError("tile is outside the offline basemap coverage")
    payload = bytes(row[0])
    if not payload or len(payload) > _MAX_TILE_BYTES:
        raise OfflineBasemapError("offline basemap tile is empty or too large")
    media_type = _FORMATS[str(pack["format"])]
    signatures = {
        "image/png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": payload.startswith(b"\xff\xd8"),
        "image/webp": payload.startswith(b"RIFF") and payload[8:12] == b"WEBP",
    }
    if not signatures[media_type]:
        raise OfflineBasemapError("offline basemap tile does not match its declared format")
    return payload, media_type
