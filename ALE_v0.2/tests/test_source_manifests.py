import hashlib
import json
from pathlib import Path

import rasterio

from ale_aam_maptool.offline_basemap import inspect_pack

ROOT = Path(__file__).resolve().parents[1]
TASKS = ("urban_drone_logistics", "cross_sea_drone_logistics", "emergency_blood_transport")


def test_supplied_airspace_archive_is_the_reviewed_snapshot():
    archive = ROOT.parent / "data" / "hong_kong_airspace_20260724.zip"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == (
        "b0cde3a908091359c1e10190d185ad74c60511cd943e5498b3c8bdd6b6f16614"
    )


def test_every_declared_gis_hash_matches_bytes():
    for task in TASKS:
        input_dir = ROOT / task / "input"
        manifest = json.loads((input_dir / "source_manifest.json").read_text(encoding="utf-8"))
        declared = {item["path"]: item["sha256"] for item in manifest["files"]}
        assert declared
        for relative, expected in declared.items():
            actual = hashlib.sha256((input_dir / "gis" / relative).read_bytes()).hexdigest()
            assert actual == expected, f"{task}: stale hash for {relative}"


def test_rfz_snapshot_and_remaining_license_blocker_are_explicit():
    for task in TASKS:
        manifest = json.loads((ROOT / task / "input" / "source_manifest.json").read_text(encoding="utf-8"))
        provenance = manifest["layer_provenance"]["airspace_zones.geojson"]
        status = provenance["status"].lower()
        assert provenance["snapshot_date"] == "2026-07-24"
        assert provenance["source_sha256"] == "b0cde3a908091359c1e10190d185ad74c60511cd943e5498b3c8bdd6b6f16614"
        assert "fixed-date" in status and "license verification" in status


def test_rfz_vectors_are_real_snapshot_clips_and_endpoints_are_outside():
    from shapely.geometry import Point, shape
    from shapely.ops import unary_union

    expected_counts = {"urban_drone_logistics": 9, "cross_sea_drone_logistics": 6,
                       "emergency_blood_transport": 26}
    for task in TASKS:
        gis = ROOT / task / "input" / "gis"
        airspace = json.loads((gis / "airspace_zones.geojson").read_text(encoding="utf-8"))
        task_data = json.loads((gis / "task.json").read_text(encoding="utf-8"))
        assert len(airspace["features"]) == expected_counts[task]
        assert not any(feature["properties"].get("benchmark_fixture")
                       for feature in airspace["features"])
        union = unary_union([shape(feature["geometry"]) for feature in airspace["features"]])
        assert not union.covers(Point(task_data["mission"]["start"]))
        assert not union.covers(Point(task_data["mission"]["goal"]))


def test_declared_raster_crs_matches_files():
    for task in TASKS:
        input_dir = ROOT / task / "input"
        manifest = json.loads((input_dir / "source_manifest.json").read_text(encoding="utf-8"))
        for name in ("dem.tif", "population_density.tif", "weather_grid.tif"):
            with rasterio.open(input_dir / "gis" / name) as dataset:
                assert str(dataset.crs) == manifest["layer_provenance"][name]["crs"]


def test_hong_kong_landsd_offline_packs_are_precise_and_auditable():
    for task in TASKS:
        directory = ROOT / task / "input" / "gis" / "basemaps"
        archive = directory / "hong_kong_landsd.mbtiles"
        sidecar = json.loads((directory / "hong_kong_landsd.manifest.json").read_text(encoding="utf-8"))
        pack = inspect_pack(archive, include_sha256=True)
        assert pack["min_zoom"] == 12 and pack["max_zoom"] == 17
        assert pack["tile_count"] == sidecar["tile_count"]
        assert pack["sha256"] == sidecar["sha256"]
        assert pack["attribution"] == "Map from Lands Department, HKSAR Government"
        assert sidecar["source"]["license"] == "DATA.GOV.HK Terms and Conditions"
        assert not (directory / "example.mbtiles").exists()
