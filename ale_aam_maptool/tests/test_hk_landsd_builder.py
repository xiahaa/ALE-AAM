import importlib.util
import io
import json
from pathlib import Path

from PIL import Image

from ale_aam_maptool.offline_basemap import inspect_pack, read_tile


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "build_hk_landsd_basemap.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("hk_landsd_builder", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _png_bytes():
    output = io.BytesIO()
    Image.new("RGB", (8, 8), (31, 119, 140)).save(output, format="PNG")
    return output.getvalue()


def test_landsd_builder_is_offline_testable_and_writes_provenance(tmp_path):
    builder = _load_builder()
    output = tmp_path / "hong_kong_landsd.mbtiles"
    requests = []

    def fake_download(zoom, x, y):
        requests.append((zoom, x, y))
        return _png_bytes(), False, False

    report = builder.create_pack(
        ROOT / "sample_scenario",
        output,
        minimum=10,
        maximum=10,
        padding=0,
        acquired_at="2026-07-28T00:00:00+00:00",
        downloader=fake_download,
    )
    pack = inspect_pack(output, include_sha256=True)
    manifest = json.loads(output.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert pack["id"] == "offline-hong-kong-landsd"
    assert pack["tile_count"] == len(requests) == report["tile_count"]
    assert pack["sha256"] == manifest["sha256"]
    assert manifest["source"]["api_template"].startswith("https://mapapi.geodata.gov.hk/")
    assert manifest["source"]["license"] == "DATA.GOV.HK Terms and Conditions"
    zoom, x, y = requests[0]
    payload, media_type = read_tile({**pack, "_path": str(output)}, zoom, x, y)
    assert media_type == "image/png" and payload.startswith(b"\x89PNG")


def test_landsd_builder_tile_order_is_deterministic():
    builder = _load_builder()
    bounds = (114.10, 22.32, 114.16, 22.35)
    first = list(builder._tile_coordinates(bounds, 12, 14))
    second = list(builder._tile_coordinates(bounds, 12, 14))
    assert first == second == sorted(first)
