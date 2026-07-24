from __future__ import annotations

import io
import os
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from PIL import Image


_ENV_KEYS = {
    "ALE_AAM_BASEMAP",
    "ALE_AAM_MAPBOX_STYLE",
    "ALE_AAM_MAPBOX_TOKEN",
    "ALE_AAM_TIANDITU_TOKEN",
}
_STYLE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+/[A-Za-z0-9_-]+$")
_MAX_TILE_BYTES = 5_000_000

_PROVIDERS = (
    {
        "id": "offline",
        "name": "离线场景图层",
        "online": False,
        "attribution": "ALE-AAM 场景数据",
        "max_zoom": 19,
    },
    {
        "id": "tianditu-vector",
        "name": "天地图·矢量",
        "online": True,
        "attribution": "天地图",
        "max_zoom": 18,
    },
    {
        "id": "tianditu-imagery",
        "name": "天地图·影像",
        "online": True,
        "attribution": "天地图",
        "max_zoom": 18,
    },
    {
        "id": "mapbox-streets",
        "name": "Mapbox·街道",
        "online": True,
        "attribution": "© Mapbox © OpenStreetMap",
        "max_zoom": 19,
    },
    {
        "id": "mapbox-satellite",
        "name": "Mapbox·卫星",
        "online": True,
        "attribution": "© Mapbox",
        "max_zoom": 19,
    },
)


class BasemapUnavailable(RuntimeError):
    """An online provider is unconfigured or could not return a safe image."""


def _env_candidates() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get("ALE_AAM_ENV_FILE")
    if explicit:
        candidates.append(Path(explicit).expanduser())
    cwd = Path.cwd()
    candidates.extend((cwd / ".env", cwd / "ale_aam_maptool" / ".env"))
    candidates.append(Path(__file__).resolve().parents[1] / ".env")
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def load_local_env() -> None:
    """Load only the four allow-listed settings without logging their values."""
    for path in _env_candidates():
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except OSError:
            continue
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key not in _ENV_KEYS:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(key, value)


load_local_env()


def _configured(provider_id: str) -> bool:
    if provider_id == "offline":
        return True
    if provider_id.startswith("tianditu-"):
        return bool(os.environ.get("ALE_AAM_TIANDITU_TOKEN", "").strip())
    if provider_id.startswith("mapbox-"):
        return bool(os.environ.get("ALE_AAM_MAPBOX_TOKEN", "").strip())
    return False


def catalog() -> dict:
    providers = [{**provider, "available": _configured(provider["id"])} for provider in _PROVIDERS]
    requested = os.environ.get("ALE_AAM_BASEMAP", "offline").strip()
    available_ids = {provider["id"] for provider in providers if provider["available"]}
    return {"default": requested if requested in available_ids else "offline", "providers": providers}


def _download_tile(url: str) -> tuple[bytes, str]:
    try:
        request = Request(url, headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": "http://127.0.0.1/",
        })
        with urlopen(request, timeout=12) as response:
            payload = response.read(_MAX_TILE_BYTES + 1)
            content_type = response.headers.get_content_type()
    except Exception:
        raise BasemapUnavailable("upstream basemap request failed") from None
    if len(payload) > _MAX_TILE_BYTES or not content_type.startswith("image/"):
        raise BasemapUnavailable("upstream basemap returned an invalid image")
    return payload, content_type


def _tianditu_url(layer: str, z: int, x: int, y: int) -> str:
    query = urlencode({
        "T": layer,
        "x": x,
        "y": y,
        "l": z,
        "tk": os.environ["ALE_AAM_TIANDITU_TOKEN"].strip(),
    })
    return f"https://t0.tianditu.gov.cn/DataServer?{query}"


def _mapbox_url(style: str, z: int, x: int, y: int) -> str:
    owner, style_id = style.split("/", 1)
    token = urlencode({"access_token": os.environ["ALE_AAM_MAPBOX_TOKEN"].strip()})
    return (
        "https://api.mapbox.com/styles/v1/"
        f"{quote(owner, safe='')}/{quote(style_id, safe='')}/tiles/256/{z}/{x}/{y}?{token}"
    )


def _compose_tianditu(base_layer: str, label_layer: str, z: int, x: int, y: int) -> tuple[bytes, str]:
    base_bytes, _ = _download_tile(_tianditu_url(base_layer, z, x, y))
    label_bytes, _ = _download_tile(_tianditu_url(label_layer, z, x, y))
    try:
        with Image.open(io.BytesIO(base_bytes)) as base_source:
            base = base_source.convert("RGBA")
        with Image.open(io.BytesIO(label_bytes)) as label_source:
            label = label_source.convert("RGBA")
        if base.size != label.size:
            raise ValueError("tile size mismatch")
        base.alpha_composite(label)
        output = io.BytesIO()
        base.save(output, format="PNG", optimize=True)
        return output.getvalue(), "image/png"
    except Exception:
        raise BasemapUnavailable("upstream basemap returned an invalid image") from None


@lru_cache(maxsize=512)
def tile(provider_id: str, z: int, x: int, y: int) -> tuple[bytes, str]:
    if not _configured(provider_id):
        raise BasemapUnavailable("basemap provider is not configured")
    if provider_id == "tianditu-vector":
        return _compose_tianditu("vec_w", "cva_w", z, x, y)
    if provider_id == "tianditu-imagery":
        return _compose_tianditu("img_w", "cia_w", z, x, y)
    if provider_id == "mapbox-streets":
        style = os.environ.get("ALE_AAM_MAPBOX_STYLE", "mapbox/streets-v12").strip()
        if not _STYLE_PATTERN.fullmatch(style):
            raise BasemapUnavailable("Mapbox style configuration is invalid")
        return _download_tile(_mapbox_url(style, z, x, y))
    if provider_id == "mapbox-satellite":
        return _download_tile(_mapbox_url("mapbox/satellite-v9", z, x, y))
    raise BasemapUnavailable("unknown basemap provider")


def provider(provider_id: str) -> dict | None:
    return next((item for item in catalog()["providers"] if item["id"] == provider_id), None)
