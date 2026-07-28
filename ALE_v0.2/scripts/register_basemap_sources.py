"""Register generated LandsD offline packs in each ALE source manifest."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASKS = ("urban_drone_logistics", "cross_sea_drone_logistics", "emergency_blood_transport")
SOURCE_NAME = "LandsD topographic map API"


def digest(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def register(task: str) -> dict:
    input_dir = ROOT / task / "input"
    gis = input_dir / "gis"
    manifest_path = input_dir / "source_manifest.json"
    sidecar_path = gis / "basemaps" / "hong_kong_landsd.manifest.json"
    archive_path = gis / "basemaps" / "hong_kong_landsd.mbtiles"
    if not sidecar_path.is_file() or not archive_path.is_file():
        raise FileNotFoundError(f"{task}: build the LandsD offline basemap first")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    if digest(archive_path) != sidecar["sha256"]:
        raise ValueError(f"{task}: basemap SHA-256 does not match its sidecar")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    source = {
        "name": SOURCE_NAME,
        "url": sidecar["source"]["api_documentation"],
        "status": "bounded z12-z17 snapshot distributed through gis/basemaps/hong_kong_landsd.mbtiles",
    }
    sources = [item for item in manifest.get("authoritative_sources", [])
               if item.get("name") != SOURCE_NAME]
    sources.append(source)
    manifest["authoritative_sources"] = sources

    step = "download a bounded, rate-limited LandsD topographic XYZ snapshot for offline visualization"
    steps = list(manifest.get("conversion_steps", []))
    if step not in steps:
        steps.append(step)
    manifest["conversion_steps"] = steps
    generated = str(manifest.get("generated_by", "")).strip()
    generator = "ale_aam_maptool/scripts/build_hk_landsd_basemap.py"
    if generator not in generated:
        manifest["generated_by"] = f"{generated} + {generator}".strip(" +")

    provenance = manifest.setdefault("layer_provenance", {})
    provenance["basemaps/hong_kong_landsd.mbtiles"] = {
        "source": sidecar["source"]["api_documentation"],
        "api_template": sidecar["source"]["api_template"],
        "license": sidecar["source"]["license"],
        "crs": sidecar["source"]["crs"],
        "attribution": sidecar["attribution"],
        "acquisition_date_utc": sidecar["acquisition_date_utc"],
        "bounds": sidecar["bounds"],
        "zoom": [sidecar["min_zoom"], sidecar["max_zoom"]],
        "tile_count": sidecar["tile_count"],
        "status": "authoritative bounded offline visualization snapshot",
    }
    manifest["files"] = [
        {"path": path.relative_to(gis).as_posix(), "sha256": digest(path)}
        for path in sorted(gis.rglob("*"))
        if path.is_file() and not path.name.startswith(".")
    ]

    payload = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    handle, temporary_name = tempfile.mkstemp(
        prefix=".source-manifest-", suffix=".json", dir=input_dir
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(temporary, manifest_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"task": task, "pack_sha256": sidecar["sha256"], "tile_count": sidecar["tile_count"]}


def main() -> None:
    reports = [register(task) for task in TASKS]
    print(json.dumps({"ok": True, "tasks": reports}, ensure_ascii=False,
                     separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
