"""Scenario contract v2. Machine coordinates are always [longitude, latitude]."""
from __future__ import annotations

from copy import deepcopy

from .errors import ConfigurationError

DEFAULT_TASK = {
    "schema_version": "2.0",
    "mission": {"id": "scenario", "name": "Scenario", "start": None, "goal": None, "environment": "urban"},
    "layers": {
        "dem": "dem.tif", "buildings": "buildings_3d.geojson",
        "airspace": "airspace_zones.geojson", "population": "population_density.tif",
        "weather": "weather_grid.tif", "emergency_sites": "emergency_sites.geojson",
    },
    "aircraft": {
        "model": "benchmark-multirotor", "cruise_speed_ms": 12.0,
        "max_speed_ms": 18.0, "cruise_power_w": 300.0, "battery_capacity_wh": 1600.0,
    },
    "constraints": {
        "altitude_m_agl": {"min": 50.0, "max": 150.0},
        "speed_ms": {"min": 5.0, "max": 18.0},
        "vertical_clearance_m": 10.0, "horizontal_clearance_m": 20.0,
        "default_building_height_m": 25.0, "noise_sensitive_pop_percentile": 80.0,
    },
    "route_profiles": {
        "A": {"objective": "shortest_direct", "strategy": "direct", "cruise_agl_m": 145.0,
              "speed_ms": 12.0, "clearance_multiplier": 1.0, "avoid_population": False},
        "B": {"objective": "conservative_safety", "strategy": "conservative", "cruise_agl_m": 100.0,
              "speed_ms": 10.0, "clearance_multiplier": 2.0, "avoid_population": False},
        "C": {"objective": "low_noise", "strategy": "mission_optimized", "cruise_agl_m": 120.0,
              "speed_ms": 11.0, "clearance_multiplier": 1.25, "avoid_population": True},
    },
}


def normalize_task(raw: dict | None) -> dict:
    raw = raw or {}
    if str(raw.get("schema_version", "")).startswith("2"):
        task = deepcopy(DEFAULT_TASK)
        for section in ("mission", "layers", "aircraft", "constraints", "route_profiles"):
            value = raw.get(section)
            if isinstance(value, dict):
                task[section].update(value)
        task["schema_version"] = str(raw.get("schema_version", "2.0"))
    else:
        task = deepcopy(DEFAULT_TASK)
        task["mission"].update({
            "start": raw.get("start"), "goal": raw.get("goal"),
            "environment": raw.get("environment", "legacy"),
        })
        task["aircraft"].update(raw.get("aircraft", {}))
        if "hover_power_w" in task["aircraft"]:
            task["aircraft"]["cruise_power_w"] = task["aircraft"].pop("hover_power_w")
        task["constraints"].update({
            "altitude_m_agl": {"min": raw.get("altitude_m_agl_min", 50), "max": raw.get("altitude_m_agl_max", 150)},
            "speed_ms": {"min": raw.get("speed_ms_min", 5), "max": raw.get("speed_ms_max", 18)},
            "vertical_clearance_m": raw.get("vertical_clearance_m", 10),
            "default_building_height_m": raw.get("default_building_height_m", 25),
            "noise_sensitive_pop_percentile": raw.get("noise_sensitive_pop_percentile", 80),
        })
    _validate(task)
    return task


def _lonlat(value, name):
    if not isinstance(value, list) or len(value) != 2:
        raise ConfigurationError(f"mission.{name} must be [longitude, latitude]")
    lon, lat = value
    if not (-180 <= float(lon) <= 180 and -90 <= float(lat) <= 90):
        raise ConfigurationError(f"mission.{name} is outside WGS84 bounds")


def _validate(task: dict):
    _lonlat(task["mission"].get("start"), "start")
    _lonlat(task["mission"].get("goal"), "goal")
    amin = float(task["constraints"]["altitude_m_agl"]["min"])
    amax = float(task["constraints"]["altitude_m_agl"]["max"])
    if not (0 <= amin <= amax <= 150):
        raise ConfigurationError("altitude envelope must satisfy 0 <= min <= max <= 150 m AGL")
    smin = float(task["constraints"]["speed_ms"]["min"])
    smax = float(task["constraints"]["speed_ms"]["max"])
    if not (0 < smin <= smax):
        raise ConfigurationError("speed envelope must satisfy 0 < min <= max")
    for name in "ABC":
        if name not in task["route_profiles"]:
            raise ConfigurationError(f"route_profiles.{name} is required")
        route = task["route_profiles"][name]
        if route.get("strategy") not in ("direct", "conservative", "mission_optimized"):
            raise ConfigurationError(f"route_profiles.{name}.strategy is invalid")
        cruise = float(route.get("cruise_agl_m", amax))
        speed = float(route.get("speed_ms", smax))
        if not amin <= cruise <= amax:
            raise ConfigurationError(f"route_profiles.{name}.cruise_agl_m is outside the altitude envelope")
        if not smin <= speed <= smax:
            raise ConfigurationError(f"route_profiles.{name}.speed_ms is outside the speed envelope")
        if float(route.get("clearance_multiplier", 1.0)) <= 0:
            raise ConfigurationError(f"route_profiles.{name}.clearance_multiplier must be positive")
        percentile = float(route.get("population_percentile", 80.0))
        if not 0 < percentile <= 100:
            raise ConfigurationError(f"route_profiles.{name}.population_percentile must be in (0, 100]")


def start_goal(task: dict):
    return task["mission"]["start"], task["mission"]["goal"]


def profile(task: dict, route: str) -> dict:
    route = route.upper()
    if route not in task["route_profiles"]:
        raise ConfigurationError(f"unknown route {route!r}; expected A, B, or C")
    return task["route_profiles"][route]
