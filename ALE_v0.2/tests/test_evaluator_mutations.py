import csv
import importlib.util
import json
import math
import shutil
from pathlib import Path

import pytest
from shapely.geometry import shape
from shapely.ops import unary_union

from ale_aam_maptool.scenario import Scenario


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v02_evaluator", ROOT / "_private/evaluator.py")
EVALUATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(EVALUATOR)


def _manual_feature(scenario, route, lateral_offset):
    start = scenario.task["mission"]["start"]
    goal = scenario.task["mission"]["goal"]
    coordinates = []
    for index in range(5):
        fraction = index / 4
        offset = math.sin(math.pi * fraction) * lateral_offset
        coordinates.append([
            start[0] + (goal[0] - start[0]) * fraction + offset,
            start[1] + (goal[1] - start[1]) * fraction,
        ])
    waypoints = []
    for index, coordinate in enumerate(coordinates):
        terrain = scenario.dem_at(coordinate)
        waypoints.append({
            "index": index,
            "altitude_m_agl": 150,
            "altitude_m_msl": (terrain if math.isfinite(terrain) else 0) + 150,
            "speed_ms": 10 + index * 0.1,
            "heading_deg": 0,
        })
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {
            "route_name": route,
            "objective": scenario.task["route_profiles"][route]["objective"],
            "estimated_energy_wh": 100,
            "waypoints": waypoints,
        },
    }


@pytest.fixture()
def manual_submission(tmp_path):
    task = ROOT / "urban_drone_logistics"
    scenario = Scenario.load(task / "input/gis")
    airspace = json.loads((task / "input/gis/airspace_zones.geojson").read_text(encoding="utf-8"))
    rfz = unary_union([shape(feature["geometry"]) for feature in airspace["features"]])
    anchors = json.loads((task / "reference/anchors.json").read_text(encoding="utf-8"))
    output = tmp_path / "output"
    output.mkdir()

    features = {
        "A": _manual_feature(scenario, "A", 0),
        "B": _manual_feature(scenario, "B", 0.0003),
        "C": _manual_feature(scenario, "C", -0.0003),
    }
    risks = {}
    totals = {}
    for route, feature in features.items():
        (output / f"route_{route.lower()}.geojson").write_text(
            json.dumps(feature), encoding="utf-8"
        )
        risks[route] = EVALUATOR.recompute_risk(feature, scenario, rfz)
        totals[route] = sum(
            risks[route][dimension] * anchors["risk_weights"][dimension]
            for dimension in EVALUATOR.DIMS
        )
    best = min(totals, key=totals.get)
    (output / "route_final.geojson").write_text(
        json.dumps(features[best]), encoding="utf-8"
    )

    fields = [
        "route", "dimension", "raw_score", "weight", "weighted_score",
        "total_score", "selected",
    ]
    with (output / "risk_assessment.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for route in "ABC":
            for dimension in EVALUATOR.DIMS:
                raw = risks[route][dimension]
                weight = anchors["risk_weights"][dimension]
                writer.writerow({
                    "route": route,
                    "dimension": dimension,
                    "raw_score": raw,
                    "weight": weight,
                    "weighted_score": raw * weight,
                    "total_score": "",
                    "selected": route == best,
                })
            writer.writerow({
                "route": route,
                "dimension": "TOTAL",
                "raw_score": "",
                "weight": "",
                "weighted_score": "",
                "total_score": totals[route],
                "selected": route == best,
            })

    terms = [
        "L1", "L2", "L3", "fault", "trigger", "communication", "recovery", "report",
        *anchors["verified_emergency_sites"],
        *anchors["required_emergency_terms"],
    ]
    (output / "emergency_response_plan.md").write_text(
        "\n".join(f"## {term}" for term in terms), encoding="utf-8"
    )
    baseline = EVALUATOR.evaluate(task / "input", output, task / "reference")
    assert baseline["components"]["files_schema"] == 1
    assert baseline["components"]["risk_and_selection"] == 1
    assert baseline["components"]["emergency"] == 1
    return task, output, baseline


def _copy_submission(manual_submission, tmp_path):
    task, source, baseline = manual_submission
    target = tmp_path / "mutated"
    shutil.copytree(source, target)
    return task, target, baseline


def test_missing_output_is_scored_without_infrastructure_error(tmp_path):
    task = ROOT / "urban_drone_logistics"
    output = tmp_path / "missing-output"
    report = EVALUATOR.evaluate(task / "input", output, task / "reference")
    assert report["score"] == 0
    assert report["components"]["files_schema"] == 0


def test_missing_file_lowers_relevant_scores_but_not_emergency(manual_submission, tmp_path):
    task, output, baseline = _copy_submission(manual_submission, tmp_path)
    (output / "route_b.geojson").unlink()
    report = EVALUATOR.evaluate(task / "input", output, task / "reference")
    assert report["components"]["files_schema"] < baseline["components"]["files_schema"]
    assert report["components"]["emergency"] == baseline["components"]["emergency"]


def test_invalid_altitude_reduces_route_constraint_score(manual_submission, tmp_path):
    task, output, baseline = _copy_submission(manual_submission, tmp_path)
    path = output / "route_a.geojson"
    feature = json.loads(path.read_text(encoding="utf-8"))
    for waypoint in feature["properties"]["waypoints"]:
        waypoint["altitude_m_agl"] = -1
    path.write_text(json.dumps(feature), encoding="utf-8")
    report = EVALUATOR.evaluate(task / "input", output, task / "reference")
    assert report["components"]["route_constraints_profiles"] < baseline["components"]["route_constraints_profiles"]


def test_fake_risk_final_and_emergency_mutations_are_local(manual_submission, tmp_path):
    task, output, baseline = _copy_submission(manual_submission, tmp_path)
    with (output / "risk_assessment.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["raw_score"] = "99"
    with (output / "risk_assessment.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    final = json.loads((output / "route_final.geojson").read_text(encoding="utf-8"))
    final["properties"]["route_name"] = "Z"
    (output / "route_final.geojson").write_text(json.dumps(final), encoding="utf-8")
    (output / "emergency_response_plan.md").write_text("L1 L2 L3", encoding="utf-8")

    report = EVALUATOR.evaluate(task / "input", output, task / "reference")
    assert report["components"]["files_schema"] == baseline["components"]["files_schema"]
    assert report["components"]["risk_and_selection"] < baseline["components"]["risk_and_selection"]
    assert report["components"]["emergency"] < baseline["components"]["emergency"]
