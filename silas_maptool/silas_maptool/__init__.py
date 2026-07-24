"""silas_maptool — low-altitude route-planning tool for the UC Berkeley ALE challenge.

It wraps the repo's jps3d JPS grid planner behind a CLI, a FastAPI HTTP API, and a
small web UI. ALE GeoJSON layers (buildings / no-fly zones) + a DEM are rasterized
to an occupancy grid; JPS finds a shortest feasible path; the result is emitted as
an ALE-contract GeoJSON route (route_a/b/c/final) with metrics.

Quick start (Python):
    from silas_maptool import Scenario, plan_route
    sc = Scenario.load("sample_scenario")
    feat = plan_route(sc, start=(114.05, 22.53), goal=(114.07, 22.54), strategy="direct")
"""
from .scenario import Scenario, PlanResult
from .planner import plan_route, plan_all_routes

__version__ = "0.2.0"
__all__ = ["Scenario", "PlanResult", "plan_route", "plan_all_routes", "__version__"]
