from __future__ import annotations

import io
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .basemaps import BasemapUnavailable, catalog as basemap_catalog, provider as basemap_provider, tile as basemap_tile
from .offline_basemap import clear_discovery_cache
from .planner import plan_all_routes, plan_route
from .scenario import Scenario
from .validator import validate_feature

WEB_DIR = Path(__file__).resolve().parent / "web"
app = FastAPI(title="ale-aam-maptool", version=__version__)
app.add_middleware(GZipMiddleware, minimum_size=1_000, compresslevel=6)
_scenario: Scenario | None = None


def bind_scenario(path, resolution=5.0):
    global _scenario
    clear_discovery_cache()
    basemap_tile.cache_clear()
    _scenario = Scenario.load(path, resolution=float(resolution))
    return _scenario


def _bound():
    if _scenario is None: raise HTTPException(503, "server has no bound scenario")
    return _scenario


def _summary(sc):
    west, south, east, north = sc.lonlat_bounds()
    return {"schema_version": sc.task["schema_version"], "mission": sc.task["mission"],
            "route_profiles": sc.task["route_profiles"], "shape": list(sc.grid.shape),
            "resolution_m": sc.grid.resolution, "crs": str(sc.grid.crs),
            "extent": {"west": west, "south": south, "east": east, "north": north},
            "constraints": sc.task["constraints"], "aircraft": sc.task["aircraft"],
            "layers": sc.layer_catalog(),
            "buildings_cells": int(sc.buildings_mask.sum()), "airspace_cells": int(sc.airspace_mask.sum())}


class PlanRequest(BaseModel):
    route: str
    densify_interval_m: float = 200.0


class ValidateRequest(BaseModel):
    feature: dict
    expected_route: str | None = None


@app.get("/v1/health")
def health(): return {"status": "ok", "version": __version__, "scenario_bound": _scenario is not None}


@app.get("/v1/scenario")
def scenario(): return _summary(_bound())


@app.get("/v1/preview")
def preview(route: str = "A"):
    sc = _bound()
    route = route.upper()
    if route not in "ABC": raise HTTPException(422, "route must be A, B, or C")
    profile = sc.task["route_profiles"][route]
    strategy = "mission_optimized" if route == "C" else profile["strategy"]
    image = sc.preview_image(strategy)
    stream = io.BytesIO(); image.save(stream, format="PNG")
    return Response(stream.getvalue(), media_type="image/png")


@app.get("/v1/layers")
def layers():
    return {"layers": _bound().layer_catalog()}


@app.get("/v1/layers/{layer_id}/preview")
def layer_preview(layer_id: str):
    try:
        image = _bound().layer_preview_image(layer_id)
    except KeyError as exc:
        raise HTTPException(404, f"unknown layer: {layer_id}") from exc
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return Response(stream.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/v1/layers/{layer_id}")
def vector_layer(layer_id: str):
    try:
        return _bound().vector_layer(layer_id)
    except KeyError as exc:
        raise HTTPException(404, f"unknown vector layer: {layer_id}") from exc


@app.get("/v1/environment")
def environment(lon: float, lat: float):
    try:
        return _bound().environment_at(lon, lat)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/v1/basemaps")
def basemaps():
    return basemap_catalog(_bound().path)


@app.get("/v1/basemaps/{provider_id}/{z}/{x}/{y}.png")
def basemap(provider_id: str, z: int, x: int, y: int):
    sc = _bound()
    definition = basemap_provider(provider_id, sc.path)
    if definition is None or provider_id == "offline" or not definition["available"]:
        raise HTTPException(404, "basemap provider unavailable")
    minimum = int(definition.get("min_zoom", 0))
    maximum = int(definition["max_zoom"])
    limit = 1 << z if minimum <= z <= maximum else 0
    if not limit or not (0 <= x < limit and 0 <= y < limit):
        raise HTTPException(422, "invalid basemap tile coordinate")
    try:
        payload, media_type = basemap_tile(provider_id, z, x, y, str(sc.path.resolve()))
    except BasemapUnavailable:
        raise HTTPException(502, "basemap tile unavailable") from None
    cache_control = "public, max-age=86400" if definition["online"] else "public, max-age=31536000, immutable"
    return Response(payload, media_type=media_type,
                    headers={"Cache-Control": cache_control})


@app.post("/v1/plan")
def plan(request: PlanRequest):
    try:
        result = plan_route(_bound(), request.route, densify_interval_m=request.densify_interval_m)
        return {"feature": result.feature, "metrics": result.metrics}
    except Exception as exc: raise HTTPException(422, str(exc)) from exc


@app.post("/v1/plan-all")
def plan_all():
    try:
        return {route: {"feature": result.feature, "metrics": result.metrics}
                for route, result in plan_all_routes(_bound()).items()}
    except Exception as exc: raise HTTPException(422, str(exc)) from exc


@app.post("/v1/validate")
def validate(request: ValidateRequest):
    errors = validate_feature(request.feature, _bound().task, request.expected_route)
    return {"ok": not errors, "errors": errors}


if WEB_DIR.exists(): app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
