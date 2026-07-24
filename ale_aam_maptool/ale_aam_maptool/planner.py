"""Route A/B/C planning driven entirely by task.json route_profiles."""
from __future__ import annotations

import math

from . import geojson_out as G
from . import metrics as M
from ._jps import load_jps
from .config import profile, start_goal
from .errors import NativeBackendError, NoFeasiblePathError
from .scenario import PlanResult, Scenario

ROUTES = ("A", "B", "C")


def _resample(points, count):
    if len(points) < 2: return points
    lengths = [math.hypot(b[0]-a[0], b[1]-a[1]) for a, b in zip(points[:-1], points[1:])]
    cumulative = [0.0]
    for length in lengths: cumulative.append(cumulative[-1] + length)
    total = cumulative[-1]
    if total <= 0: return [points[0]] * count
    output, segment = [], 0
    for index in range(count):
        target = total * index / max(1, count - 1)
        while segment < len(lengths)-1 and target > cumulative[segment+1]: segment += 1
        fraction = (target-cumulative[segment]) / max(lengths[segment], 1e-12)
        a, b = points[segment], points[segment+1]
        output.append((a[0]+fraction*(b[0]-a[0]), a[1]+fraction*(b[1]-a[1])))
    return output


def _native_plan(grid, start, goal):
    try:
        result = load_jps().plan_2d(grid.origin, grid.dim, grid.map_data, list(start), list(goal), grid.resolution, True)
    except ImportError:
        raise
    except Exception as exc:
        raise NativeBackendError(str(exc)) from exc
    if getattr(result, "status", 0) not in (0, None) or not getattr(result, "success", bool(result.path)):
        return [], float(getattr(result, "time_spent", 0.0)), getattr(result, "message", "no feasible path")
    return [(float(p[0]), float(p[1])) for p in result.path], float(result.time_spent), "ok"


def plan_route(scenario: Scenario, route: str, *, densify_interval_m=200.0, retries=False):
    route = route.upper()
    route_profile = profile(scenario.task, route)
    strategy = str(route_profile.get("strategy", "direct"))
    grid_strategy = "mission_optimized" if route == "C" else strategy
    start, goal = start_goal(scenario.task)
    start_m, goal_m = scenario.to_metric(*start), scenario.to_metric(*goal)
    base = float(scenario.task["constraints"].get("horizontal_clearance_m", 20.0))
    clearance = base * float(route_profile.get("clearance_multiplier", 1.0))
    attempts = [(clearance, bool(route_profile.get("avoid_population", False)))]
    if route_profile.get("avoid_population", False):
        # Population is an optimization objective, not a hard safety constraint.
        # If the highest-density cells disconnect the grid, retain all hard
        # clearances and find the least-distance feasible path without that mask.
        attempts.append((clearance, False))
    if retries:
        attempts += [(clearance * 0.5, False), (0.0, False)]
    path = []
    message = "no feasible path"
    planning_ms = 0.0
    population_hard_avoidance = False
    for extra, avoid_population in attempts:
        occupancy = scenario.occupancy(
            grid_strategy, extra_clearance_m=extra,
            pop_block=avoid_population,
            pop_percentile=route_profile.get("population_percentile"),
            cruise_agl=float(route_profile.get("cruise_agl_m", 120.0)),
            force_free_lonlat=[start, goal],
        )
        path, planning_ms, message = _native_plan(occupancy, start_m, goal_m)
        if len(path) >= 2:
            population_hard_avoidance = avoid_population
            break
    if len(path) < 2:
        raise NoFeasiblePathError(f"route {route}: {message}")
    path[0], path[-1] = start_m, goal_m
    total = sum(math.hypot(b[0]-a[0], b[1]-a[1]) for a, b in zip(path[:-1], path[1:]))
    sampled = _resample(path, max(5, int(math.ceil(total / densify_interval_m)) + 1))
    sampled[0], sampled[-1] = start_m, goal_m
    coords = [list(scenario.to_lonlat(x, y)) for x, y in sampled]
    coords[0], coords[-1] = list(start), list(goal)
    waypoints = M.build_waypoints(coords, route_profile, scenario)
    metrics = M.route_metrics(coords, waypoints, scenario.task)
    feature = G.build_feature(route, strategy, str(route_profile.get("objective", strategy)), coords, waypoints, metrics,
                              {"population_hard_avoidance": population_hard_avoidance})
    return PlanResult(feature, metrics, coords, strategy, planning_ms)


def plan_all_routes(scenario, **kwargs):
    return {route: plan_route(scenario, route, **kwargs) for route in ROUTES}


plan_all_strategies = plan_all_routes
