import hashlib
import json
from pathlib import Path

import rasterio

ROOT = Path(__file__).resolve().parents[1]
TASKS = ("urban_drone_logistics", "cross_sea_drone_logistics", "emergency_blood_transport")


def test_every_declared_gis_hash_matches_bytes():
    for task in TASKS:
        input_dir = ROOT / task / "input"
        manifest = json.loads((input_dir / "source_manifest.json").read_text(encoding="utf-8"))
        declared = {item["path"]: item["sha256"] for item in manifest["files"]}
        assert declared
        for relative, expected in declared.items():
            actual = hashlib.sha256((input_dir / "gis" / relative).read_bytes()).hexdigest()
            assert actual == expected, f"{task}: stale hash for {relative}"


def test_rfz_publication_blocker_is_explicit():
    for task in TASKS:
        manifest = json.loads((ROOT / task / "input" / "source_manifest.json").read_text(encoding="utf-8"))
        status = manifest["layer_provenance"]["airspace_zones.geojson"]["status"].lower()
        assert "fixture" in status and "must be replaced" in status


def test_declared_raster_crs_matches_files():
    for task in TASKS:
        input_dir = ROOT / task / "input"
        manifest = json.loads((input_dir / "source_manifest.json").read_text(encoding="utf-8"))
        for name in ("dem.tif", "population_density.tif", "weather_grid.tif"):
            with rasterio.open(input_dir / "gis" / name) as dataset:
                assert str(dataset.crs) == manifest["layer_provenance"][name]["crs"]
