"""Public validation: schema and explicit hard constraints only (no scoring)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

REQUIRED_FILES = (
    "route_a.geojson", "route_b.geojson", "route_c.geojson", "route_final.geojson",
    "risk_assessment.csv", "emergency_response_plan.md",
)


def validate_feature(feature: dict, task: dict, expected_route: str | None = None) -> list[str]:
    errors = []
    if feature.get("type") != "Feature" or feature.get("geometry", {}).get("type") != "LineString":
        return ["route must be a GeoJSON Feature with LineString geometry"]
    coords = feature["geometry"].get("coordinates", [])
    props = feature.get("properties", {})
    if len(coords) < 5: errors.append("route must contain at least five coordinates")
    if any(not isinstance(p, list) or len(p) != 2 or not (-180 <= p[0] <= 180 and -90 <= p[1] <= 90) for p in coords):
        errors.append("coordinates must be [longitude, latitude] in WGS84 bounds")
    planning_bounds = (task.get("planning_extent") or {}).get("bounds_wgs84")
    if isinstance(planning_bounds, list) and len(planning_bounds) == 4:
        west, south, east, north = planning_bounds
        if any(not (west <= point[0] <= east and south <= point[1] <= north)
                   for point in coords if isinstance(point, list) and len(point) == 2):
            errors.append("coordinates must remain inside planning_extent bounds_wgs84")
    start, goal = task["mission"]["start"], task["mission"]["goal"]
    if coords and any(abs(coords[0][i] - start[i]) > 1e-6 for i in range(2)): errors.append("start endpoint mismatch")
    if coords and any(abs(coords[-1][i] - goal[i]) > 1e-6 for i in range(2)): errors.append("goal endpoint mismatch")
    if expected_route and props.get("route_name") != expected_route: errors.append("route_name mismatch")
    waypoints = props.get("waypoints", [])
    if len(waypoints) != len(coords): errors.append("waypoints length must match coordinates")
    amin = task["constraints"]["altitude_m_agl"]["min"]
    amax = task["constraints"]["altitude_m_agl"]["max"]
    smin = task["constraints"]["speed_ms"]["min"]
    smax = task["constraints"]["speed_ms"]["max"]
    for i, waypoint in enumerate(waypoints):
        if not (amin <= waypoint.get("altitude_m_agl", -1) <= amax): errors.append(f"waypoint {i} violates AGL envelope")
        if "altitude_m_msl" not in waypoint: errors.append(f"waypoint {i} lacks altitude_m_msl")
        if not (smin <= waypoint.get("speed_ms", -1) <= smax): errors.append(f"waypoint {i} violates speed envelope")
    return errors


def validate_output(output_dir, task: dict) -> dict:
    directory = Path(output_dir)
    errors, files = [], {}
    for name in REQUIRED_FILES:
        path = directory / name
        files[name] = path.exists() and path.stat().st_size > 0
        if not files[name]: errors.append(f"missing or empty {name}")
    features = {}
    for route in "abc":
        path = directory / f"route_{route}.geojson"
        if path.exists():
            try:
                feature = json.loads(path.read_text(encoding="utf-8"))
                features[route.upper()] = feature
                errors.extend(f"route_{route}: {e}" for e in validate_feature(feature, task, route.upper()))
            except Exception as exc: errors.append(f"route_{route}: invalid JSON: {exc}")
    final = directory / "route_final.geojson"
    if final.exists():
        try:
            final_feature = json.loads(final.read_text(encoding="utf-8"))
            errors.extend(f"route_final: {e}" for e in validate_feature(final_feature, task))
            if final_feature.get("properties", {}).get("route_name") not in features:
                errors.append("route_final route_name must select A, B, or C")
        except Exception as exc: errors.append(f"route_final: invalid JSON: {exc}")
    risk = directory / "risk_assessment.csv"
    if risk.exists():
        try:
            rows = list(csv.reader(risk.open(encoding="utf-8", newline="")))
            if len(rows) != 22: errors.append("risk_assessment.csv must have one header plus 21 rows")
        except Exception as exc: errors.append(f"risk_assessment.csv: {exc}")
    return {"ok": not errors, "schema_version": "2.0", "files": files, "errors": errors}
