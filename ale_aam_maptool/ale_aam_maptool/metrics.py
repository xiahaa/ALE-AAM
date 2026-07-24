"""Deterministic WGS84 route metrics and AGL/MSL waypoint attributes."""
from __future__ import annotations

import math
from pyproj import Geod

_GEOD = Geod(ellps="WGS84")


def segment_azimuth_deg(p0, p1):
    az, _, _ = _GEOD.inv(p0[0], p0[1], p1[0], p1[1])
    return round(az % 360.0, 1)


def polyline_distance_m(path):
    return sum(_GEOD.inv(a[0], a[1], b[0], b[1])[2] for a, b in zip(path[:-1], path[1:]))


def build_waypoints(path, route_profile, scenario):
    constraints = scenario.task["constraints"]
    amin = float(constraints["altitude_m_agl"]["min"])
    amax = float(constraints["altitude_m_agl"]["max"])
    agl = min(amax, max(amin, float(route_profile.get("cruise_agl_m", amax))))
    smin = float(constraints["speed_ms"]["min"])
    smax = float(constraints["speed_ms"]["max"])
    speed = min(smax, max(smin, float(route_profile.get("speed_ms", scenario.task["aircraft"]["cruise_speed_ms"]))))
    out = []
    for index, ll in enumerate(path):
        terrain = scenario.dem_at(ll)
        if not math.isfinite(terrain):
            terrain = 0.0
        heading = segment_azimuth_deg(ll, path[index + 1]) if index + 1 < len(path) else 0.0
        out.append({
            "index": index,
            "altitude_m_agl": round(agl, 1),
            "altitude_m_msl": round(terrain + agl, 1),
            "speed_ms": round(speed, 2),
            "heading_deg": heading,
        })
    return out


def route_metrics(path, waypoints, task):
    distance = polyline_distance_m(path)
    speed = float(waypoints[0]["speed_ms"]) if waypoints else 0.0
    duration = distance / speed if speed > 0 else 0.0
    power = float(task["aircraft"].get("cruise_power_w", 300.0))
    energy = power * duration * 1.2 / 3600.0
    return {
        "total_distance_m": round(distance, 2),
        "estimated_duration_s": round(duration, 2),
        "estimated_energy_wh": round(energy, 2),
        "battery_capacity_wh": float(task["aircraft"].get("battery_capacity_wh", 1600.0)),
        "n_waypoints": len(path),
    }
