"""Clip the supplied 2026-07-24 Hong Kong RFZ snapshot into all ALE cases."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

import rasterio
from rasterio.warp import transform_bounds
from shapely.geometry import Point, box, mapping, shape
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT.parent / "data" / "hong_kong_airspace_20260724.zip"
ARCHIVE_SHA256 = "b0cde3a908091359c1e10190d185ad74c60511cd943e5498b3c8bdd6b6f16614"
TASKS = ("urban_drone_logistics", "cross_sea_drone_logistics", "emergency_blood_transport")
GOAL_OVERRIDES = {
    # The former point was inside the Cheung Chau Helipad RFZ. This reviewed
    # point is ~268 m west, inside the DTM and outside every supplied RFZ/building.
    "cross_sea_drone_logistics": [114.0286329722111, 22.208092486108427],
}


def digest(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def round_coordinates(value):
    if isinstance(value, (list, tuple)):
        return [round_coordinates(item) for item in value]
    if isinstance(value, float):
        return round(value, 8)
    return value


def polygonal_intersection(geometry, region):
    clipped = geometry.buffer(0).intersection(region)
    if clipped.is_empty:
        return None
    if clipped.geom_type == "GeometryCollection":
        polygons = [item for item in clipped.geoms
                    if item.geom_type in {"Polygon", "MultiPolygon"}]
        clipped = unary_union(polygons) if polygons else None
    return clipped if clipped is not None and not clipped.is_empty else None


def atomic_json(path: Path, data: dict) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".json", dir=path.parent)
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def source_features() -> list[dict]:
    if digest(ARCHIVE) != ARCHIVE_SHA256:
        raise ValueError("Hong Kong airspace archive SHA-256 is not the reviewed snapshot")
    with zipfile.ZipFile(ARCHIVE) as bundle:
        data = json.loads(bundle.read("GeoJSON/map.geojson"))
    features = data.get("features", [])
    if len(features) != 283 or any(shape(item["geometry"]).geom_type != "Polygon" for item in features):
        raise ValueError("Hong Kong airspace archive does not match the reviewed 283-polygon layout")
    return features


def update_manifest(task_root: Path, feature_count: int) -> None:
    manifest_path = task_root / "input" / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = str(manifest.get("actual_derivation", ""))
    if "; RFZ remains" in actual:
        actual = actual.split("; RFZ remains", 1)[0]
    manifest["actual_derivation"] = (
        f"{actual}; RFZ uses the clipped, fixed-date user-provided 2026-07-24 snapshot"
    ).strip("; ")
    source_name = "CAD/eSUA RFZ fixed-date export"
    source = {
        "name": source_name,
        "url": "https://esua.cad.gov.hk/web/droneMap",
        "status": "user-provided 2026-07-24 snapshot distributed as gis/airspace_zones.geojson; source redistribution terms must be confirmed before publication",
    }
    key = "authoritative_sources" if "authoritative_sources" in manifest else "authoritative_replacement_sources"
    sources = [item for item in manifest.get(key, [])
               if item.get("name") not in {source_name, "CAD eSUA RFZ map"}]
    sources.append(source)
    manifest[key] = sources
    steps = list(manifest.get("conversion_steps", []))
    step = "verify the supplied archive SHA-256, repair polygon topology, clip RFZs to the DEM extent, and sort deterministically"
    if step not in steps:
        steps.append(step)
    manifest["conversion_steps"] = steps
    generated = str(manifest.get("generated_by", "")).strip()
    generator = "scripts/import_hk_airspace_snapshot.py"
    if generator not in generated:
        manifest["generated_by"] = f"{generated} + {generator}".strip(" +")
    manifest.setdefault("layer_provenance", {})["airspace_zones.geojson"] = {
        "source": "data/hong_kong_airspace_20260724.zip",
        "source_url": "https://esua.cad.gov.hk/web/droneMap",
        "source_sha256": ARCHIVE_SHA256,
        "snapshot_date": "2026-07-24",
        "crs": "EPSG:4326",
        "feature_count": feature_count,
        "license": "Source redistribution terms must be confirmed before benchmark publication",
        "status": "fixed-date user-provided RFZ snapshot; license verification remains a publication blocker",
    }
    gis = task_root / "input" / "gis"
    manifest["files"] = [
        {"path": path.relative_to(gis).as_posix(), "sha256": digest(path)}
        for path in sorted(gis.rglob("*"))
        if path.is_file() and not path.name.startswith(".")
    ]
    atomic_json(manifest_path, manifest)


def import_task(task: str, source: list[dict]) -> dict:
    task_root = ROOT / task
    gis = task_root / "input" / "gis"
    with rasterio.open(gis / "dem.tif") as dataset:
        bounds = transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds, densify_pts=21)
    region = box(*bounds)
    clipped = []
    for feature in source:
        geometry = polygonal_intersection(shape(feature["geometry"]), region)
        if geometry is None:
            continue
        properties = dict(feature.get("properties") or {})
        properties.update({
            "snapshot_date": "2026-07-24",
            "source": "Hong Kong eSUA/RFZ user-provided fixed-date export",
            "source_archive_sha256": ARCHIVE_SHA256,
            "zone_type": properties.get("type", "RFZ"),
        })
        clipped.append({
            "type": "Feature",
            "geometry": round_coordinates(mapping(geometry)),
            "properties": properties,
        })
    clipped.sort(key=lambda item: (
        int(item["properties"].get("index", 0)),
        str(item["properties"].get("name", "")),
        json.dumps(item["geometry"], sort_keys=True),
    ))
    collection = {
        "type": "FeatureCollection",
        "name": f"Hong Kong RFZ snapshot clipped for {task}",
        "snapshot_date": "2026-07-24",
        "source_archive": "data/hong_kong_airspace_20260724.zip",
        "source_archive_sha256": ARCHIVE_SHA256,
        "features": clipped,
    }
    atomic_json(gis / "airspace_zones.geojson", collection)

    task_path = gis / "task.json"
    task_data = json.loads(task_path.read_text(encoding="utf-8"))
    if task in GOAL_OVERRIDES:
        task_data["mission"]["goal"] = GOAL_OVERRIDES[task]
        atomic_json(task_path, task_data)
    union = unary_union([shape(item["geometry"]) for item in clipped])
    for endpoint_name in ("start", "goal"):
        if union.covers(Point(task_data["mission"][endpoint_name])):
            raise ValueError(f"{task}: {endpoint_name} remains inside an RFZ")
    update_manifest(task_root, len(clipped))
    return {"task": task, "features": len(clipped), "goal": task_data["mission"]["goal"]}


def main() -> None:
    source = source_features()
    reports = [import_task(task, source) for task in TASKS]
    print(json.dumps({"ok": True, "source_features": len(source), "tasks": reports},
                     ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
