"""Deterministically build the three v0.2 staged-data bundles.

The present repository does not redistribute the large authoritative Hong Kong
source archives. For reproducible code review, this builder affine-transforms the
v0.1 benchmark fixture geometry/raster values onto the corrected Hong Kong mission
footprints and records that derivation explicitly. ``source_manifest.json`` lists
the authoritative replacement sources and never presents the fixture as operational
government data.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_bounds

ROOT = Path(__file__).resolve().parents[1]
V01 = ROOT.parent / "ALE_v0.1"

TASKS = {
    "urban_drone_logistics": {
        "title": "Hong Kong Kowloon Urban Drone Logistics",
        "summary": "Plan and assess three low-altitude logistics routes across a dense Kowloon urban corridor.",
        "source": "urban_drone_logistics", "start": [114.1100062342439, 22.33649759809088],
        "goal": [114.14639844489409, 22.33705333134389], "bounds": [114.101, 22.326, 114.156, 22.348],
        "environment": "kowloon_urban", "c_objective": "low_noise", "c_speed": 10.0,
        "special": ["open space", "dense urban", "pedestrian cordon"],
    },
    "cross_sea_drone_logistics": {
        "title": "Hong Kong Southern Cross-sea Drone Logistics",
        "summary": "Plan and assess three low-altitude logistics routes across southern Hong Kong waters.",
        "source": "cross_sea_drone_logistics", "start": [114.12953776982366, 22.260497414234752],
        "goal": [114.0312329722111, 22.208092486108427], "bounds": [114.018, 22.196, 114.142, 22.272],
        "environment": "southern_cross_sea", "c_objective": "wind_energy_optimized", "c_speed": 13.0,
        "special": ["water ditching", "marine rescue", "wind contingency"],
    },
    "emergency_blood_transport": {
        "title": "Hong Kong Island Emergency Blood Transport",
        "summary": "Plan time-critical blood transport routes on Hong Kong Island with cold-chain contingencies.",
        "source": "emergency_blood_transport", "start": [114.15669210740508, 22.28314128069164],
        "goal": [114.17545103104615, 22.27613299225955], "bounds": [114.149, 22.270, 114.183, 22.290],
        "environment": "hong_kong_island_emergency", "c_objective": "time_optimal", "c_speed": 16.0,
        "special": ["cold chain", "2-8 C", "hospital handover"],
    },
}

OFFICIAL_SOURCES = [
    {"name": "LandsD 5 m DTM", "url": "https://data.gov.hk/en-data/dataset/hk-landsd-openmap-5m-grid-dtm", "status": "authoritative replacement source; not redistributed in this fixture"},
    {"name": "LandsD building data with height", "url": "https://data.gov.hk/en-data/dataset/hk-landsd-openmap-landsd-building", "status": "authoritative replacement source; not redistributed in this fixture"},
    {"name": "CAD eSUA RFZ map", "url": "https://esua.cad.gov.hk/web/droneMap", "status": "fixed-date export required before benchmark publication"},
    {"name": "HKO latest ten-minute wind", "url": "https://data.gov.hk/en-data/dataset/hk-hko-rss-latest-ten-minute-wind-info", "status": "authoritative replacement source"},
    {"name": "2021 Population Census", "url": "https://data.gov.hk/en-data/dataset/hk-censtatd-census_geo-2021-population-census-by-dcd", "status": "authoritative replacement source"},
]


def transform_coord(value, old, new):
    x, y = value[:2]
    nx = new[0] + (x-old[0]) / (old[2]-old[0]) * (new[2]-new[0])
    ny = new[1] + (y-old[1]) / (old[3]-old[1]) * (new[3]-new[1])
    return [round(nx, 8), round(ny, 8), *value[2:]]


def transform_geometry(geometry, old, new):
    def walk(value):
        if value and isinstance(value[0], (int, float)): return transform_coord(value, old, new)
        return [walk(item) for item in value]
    result = dict(geometry); result["coordinates"] = walk(geometry["coordinates"]); return result


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_gis(name, cfg, destination):
    source = V01 / cfg["source"] / "input" / "gis"
    with rasterio.open(source / "dem.tif") as raster:
        old_bounds = list(raster.bounds)
    for filename in ("buildings_3d.geojson", "airspace_zones.geojson"):
        data = json.loads((source / filename).read_text(encoding="utf-8"))
        for feature in data.get("features", []):
            feature["geometry"] = transform_geometry(feature["geometry"], old_bounds, cfg["bounds"])
            if filename.startswith("airspace"):
                feature.setdefault("properties", {})["snapshot_date"] = "2026-07-01"
                feature["properties"]["benchmark_fixture"] = True
        write_json(destination / filename, data)
    for filename in ("dem.tif", "population_density.tif"):
        with rasterio.open(source / filename) as raster:
            values, profile = raster.read(1), raster.profile.copy()
        profile.update(transform=from_bounds(*cfg["bounds"], values.shape[1], values.shape[0]), crs="EPSG:4326", nodata=-9999.0)
        with rasterio.open(destination / filename, "w", **profile) as output: output.write(values, 1)
    with rasterio.open(destination / "dem.tif") as raster:
        shape, profile = (raster.height, raster.width), raster.profile.copy()
    yy, xx = np.indices(shape)
    weather = (4.0 + 3.0 * xx / max(1, shape[1]-1) + 1.5 * yy / max(1, shape[0]-1)).astype("float32")
    profile.update(dtype="float32", count=1, nodata=-9999.0)
    with rasterio.open(destination / "weather_grid.tif", "w", **profile) as output: output.write(weather, 1)
    west, south, east, north = cfg["bounds"]
    sites = []
    for index, (fx, fy, kind) in enumerate(((.25,.25,"open_space"),(.50,.55,"helipad"),(.72,.32,"sports_ground"),(.82,.70,"marine_or_rooftop")), 1):
        sites.append({"type":"Feature","geometry":{"type":"Point","coordinates":[round(west+fx*(east-west),8),round(south+fy*(north-south),8)]},
                      "properties":{"site_id":f"{name[:3].upper()}-{index}","verified_for_benchmark":True,"site_type":kind}})
    write_json(destination / "emergency_sites.geojson", {"type":"FeatureCollection","features":sites})


def task_json(name, cfg):
    return {
        "schema_version":"2.0", "mission":{"id":name,"name":cfg["title"],"start":cfg["start"],"goal":cfg["goal"],"environment":cfg["environment"]},
        "layers":{"dem":"dem.tif","buildings":"buildings_3d.geojson","airspace":"airspace_zones.geojson","population":"population_density.tif","weather":"weather_grid.tif","emergency_sites":"emergency_sites.geojson"},
        "aircraft":{"model":"AAM-MR-40 simulation","cruise_speed_ms":12,"max_speed_ms":18,"cruise_power_w":650,"battery_capacity_wh":2200},
        "constraints":{"altitude_m_agl":{"min":50,"max":150},"speed_ms":{"min":5,"max":18},"vertical_clearance_m":15,"horizontal_clearance_m":25,"default_building_height_m":25,"noise_sensitive_pop_percentile":80},
        "route_profiles":{
            "A":{"objective":"shortest_direct","strategy":"direct","cruise_agl_m":145,"speed_ms":14,"clearance_multiplier":1,"avoid_population":False},
            "B":{"objective":"conservative_safety","strategy":"conservative","cruise_agl_m":145 if name=="emergency_blood_transport" else 110,"speed_ms":10,"clearance_multiplier":2,"avoid_population":False},
            "C":{"objective":cfg["c_objective"],"strategy":"mission_optimized","cruise_agl_m":125,"speed_ms":cfg["c_speed"],"clearance_multiplier":1.25,"avoid_population":name=="urban_drone_logistics","population_percentile":90 if name=="urban_drone_logistics" else 99},
        },
    }


def documents(name, cfg):
    prompt = f"""# {cfg['title']}

This is a benchmark simulation, not a real flight authorization. The 50–150 m
AGL envelope is a hypothetical advanced-operations permission; do not describe it
as the general legal limit.

Use only `[longitude, latitude]`. Inspect `gis/task.json`, then create three
materially different candidates: A shortest direct, B conservative with double
horizontal clearance, and C `{cfg['c_objective']}`. Recompute risk from your own
submitted routes and select the lowest defensible total-risk route.

Deliver exactly six files in `output/`: `route_a.geojson`, `route_b.geojson`,
`route_c.geojson`, `route_final.geojson`, `risk_assessment.csv`, and
`emergency_response_plan.md`. The CSV has one header plus exactly 21 data rows.
Every waypoint has both `altitude_m_agl` and `altitude_m_msl`.
"""
    contract = {
        "schema_version":"2.0", "coordinate_order":["longitude","latitude"], "required_files":["route_a.geojson","route_b.geojson","route_c.geojson","route_final.geojson","risk_assessment.csv","emergency_response_plan.md"],
        "route":{"type":"GeoJSON Feature/LineString","minimum_coordinates":5,"waypoint_fields":["index","altitude_m_agl","altitude_m_msl","speed_ms","heading_deg"]},
        "risk_csv":{"rows_excluding_header":21,"columns":["route","dimension","raw_score","weight","weighted_score","total_score","selected"],"dimensions":["collision","terrain","population","weather","noise","energy"]},
    }
    routing = f"""# Routing guidelines

- A: shortest feasible direct candidate.
- B: conservative safety candidate; clearance multiplier is exactly 2.0.
- C: `{cfg['c_objective']}` for this scenario.
- All routes must avoid RFZ polygons, respect building height plus 15 m vertical
  clearance, remain in the 50–150 m AGL and 5–18 m/s envelopes, fit battery
  capacity, start/end exactly at task.json coordinates, and differ materially.
- `ale-aam-maptool validate` checks public schema and explicit constraints only; it
  is not a reference-answer or grading command.
"""
    rubric = """# Risk worksheet

For each of A/B/C calculate six raw scores in [0,1]: collision, terrain,
population exposure, weather, noise, and energy. Use weights 0.30, 0.10, 0.20,
0.15, 0.10, 0.15. `weighted_score = raw_score * weight`; the six weighted
scores sum to the route total. Write six dimension rows plus one TOTAL row per
route (21 rows). Select exactly one route, and make route_final.geojson byte-level
geometry-equivalent to that candidate. Do not invent measurements not derivable
from the staged GIS and submitted routes.
"""
    emergency = f"""# Emergency response requirements

Include: mission/route segmentation; L1/L2/L3 definitions; a fault matrix with at
least five distinct faults and trigger/action/authority/communication columns;
primary and backup communications; command and handover; recovery/reporting; and
at least three sites whose coordinates and `site_id` match
`gis/emergency_sites.geojson`. Scenario-specific content must explicitly cover:
{', '.join(cfg['special'])}. Coordinates remain `[longitude, latitude]`.
"""
    usage = """# Tool use (offline)

The staged `software/wheelhouse/` contains wheels. `start()` installs them into
`software/.venv` with `--no-index --only-binary=:all:`. Use
`software/.venv/bin/ale-aam-maptool doctor --json`, `inspect`, `plan-all`, `grid`,
and `validate`. Do not use network access, sudo, apt, Homebrew, MSVC, or a source
compiler. The web demo is `serve --scenario input/gis --host 127.0.0.1`.
"""
    return {"task_prompt.md":prompt,"output_contract.json":json.dumps(contract,indent=2),"routing_guidelines.md":routing,
            "risk_assessment_rubric.md":rubric,"emergency_planning_manual.md":emergency,"tool_usage.md":usage}


def build():
    for name, cfg in TASKS.items():
        root, gis = ROOT / name, ROOT / name / "input" / "gis"
        gis.mkdir(parents=True, exist_ok=True)
        build_gis(name, cfg, gis)
        write_json(gis / "task.json", task_json(name, cfg))
        for filename, content in documents(name, cfg).items():
            path = root / "input" / filename; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content.rstrip()+"\n", encoding="utf-8")
        data_files = sorted(p for p in gis.iterdir() if p.is_file())
        manifest = {"schema_version":"1.0","operational_use":False,"generated_by":"scripts/build_tasks.py",
                    "actual_derivation":"deterministic affine transform of ALE_v0.1 fixtures onto corrected Hong Kong mission footprint; not authoritative Hong Kong GIS",
                    "crs":"EPSG:4326 for vectors and fixture rasters; tool projects to local UTM with always_xy=True",
                    "conversion_steps":["affine coordinate transform","deterministic raster georeferencing","deterministic weather surface","SHA-256 inventory"],
                    "authoritative_replacement_sources":OFFICIAL_SOURCES,
                    "files":[{"path":p.name,"sha256":sha(p)} for p in data_files]}
        write_json(root / "input" / "source_manifest.json", manifest)
        anchors = {"schema_version":"2.0","route_geometry_reference":None,"tolerances":{"endpoint_m":3,"risk_raw":0.15,"arithmetic":0.01},
                   "risk_weights":{"collision":.30,"terrain":.10,"population":.20,"weather":.15,"noise":.10,"energy":.15},
                   "verified_emergency_sites":[f["properties"]["site_id"] for f in json.loads((gis/"emergency_sites.geojson").read_text())["features"]],
                   "required_emergency_terms":cfg["special"],"expert_metric_ranges":{"straight_line_factor":[1.0,2.5],"battery_fraction":[0.0,0.9]}}
        write_json(root / "reference" / "anchors.json", anchors)
        card = {"taskId":f"transport_safety/{name}","title":cfg["title"],"summary":cfg["summary"],"category":"transport_safety",
                "vm":{"snapshot":"cpu-free-ubuntu","vcpus":8,"memory_gb":32,"disk_gb":200,"timeout_s":14400}}
        write_json(root / "task_card.json", card)
        template=(ROOT/"scripts"/"main_template.py.in").read_text(encoding="utf-8")
        template=template.replace("@@TASK_NAME@@",name).replace("@@TITLE@@",cfg["title"]).replace("@@SUMMARY@@",cfg["summary"])
        (root/"main.py").write_text(template,encoding="utf-8",newline="\n")


if __name__ == "__main__": build()
