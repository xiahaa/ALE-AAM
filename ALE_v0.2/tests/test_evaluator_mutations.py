import csv
import importlib.util
import json
import shutil
from pathlib import Path

import pytest
from shapely.geometry import shape
from shapely.ops import unary_union

from silas_maptool.planner import plan_all_routes
from silas_maptool.scenario import Scenario

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("v02_evaluator", ROOT / "_private/evaluator.py")
E = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(E)


@pytest.fixture(scope="module")
def expert(tmp_path_factory):
    output = tmp_path_factory.mktemp("expert")
    task = ROOT / "urban_drone_logistics"
    scenario = Scenario.load(task / "input/gis")
    routes = plan_all_routes(scenario)
    for name, result in routes.items():
        (output / f"route_{name.lower()}.geojson").write_text(json.dumps(result.feature))
    air = json.loads((task / "input/gis/airspace_zones.geojson").read_text())
    rfz = unary_union([shape(f["geometry"]) for f in air["features"]])
    anchors = json.loads((task / "reference/anchors.json").read_text())
    risks = {name:E.recompute_risk(result.feature, scenario, rfz) for name,result in routes.items()}
    totals = {name:sum(values[d]*anchors["risk_weights"][d] for d in E.DIMS) for name,values in risks.items()}
    best = min(totals, key=totals.get)
    shutil.copyfile(output / f"route_{best.lower()}.geojson", output / "route_final.geojson")
    with (output / "risk_assessment.csv").open("w", newline="", encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=["route","dimension","raw_score","weight","weighted_score","total_score","selected"]); writer.writeheader()
        for route in "ABC":
            for dim in E.DIMS:
                raw=risks[route][dim]; weight=anchors["risk_weights"][dim]
                writer.writerow({"route":route,"dimension":dim,"raw_score":raw,"weight":weight,"weighted_score":raw*weight,"total_score":"","selected":route==best})
            writer.writerow({"route":route,"dimension":"TOTAL","raw_score":"","weight":"","weighted_score":"","total_score":totals[route],"selected":route==best})
    terms=["L1","L2","L3","fault trigger communication recovery report",*anchors["verified_emergency_sites"],*anchors["required_emergency_terms"]]
    (output / "emergency_response_plan.md").write_text("\n".join(f"## {term}" for term in terms))
    report=E.evaluate(task/"input",output,task/"reference")
    assert report["score"] == 1.0, report
    return task,output,report


def mutate(expert,tmp_path):
    task,source,_=expert; target=tmp_path/"output"; shutil.copytree(source,target); return task,target


def test_missing_file_lowers_only_related_components(expert,tmp_path):
    task,out=mutate(expert,tmp_path); (out/"route_b.geojson").unlink()
    report=E.evaluate(task/"input",out,task/"reference")
    assert report["components"]["files_schema"]<1 and report["components"]["emergency"]==1


def test_clearance_and_rfz_mutations_reduce_route_score(expert,tmp_path):
    task,out=mutate(expert,tmp_path); path=out/"route_a.geojson"; data=json.loads(path.read_text())
    for waypoint in data["properties"]["waypoints"]: waypoint["altitude_m_agl"]=50
    zone=json.loads((task/"input/gis/airspace_zones.geojson").read_text())["features"][0]
    data["geometry"]["coordinates"][2]=list(shape(zone["geometry"]).centroid.coords[0]); path.write_text(json.dumps(data))
    assert E.evaluate(task/"input",out,task/"reference")["components"]["route_constraints_profiles"]<1


def test_fake_risk_final_and_emergency_mutations_are_local(expert,tmp_path):
    task,out=mutate(expert,tmp_path)
    rows=list(csv.DictReader((out/"risk_assessment.csv").open())); rows[0]["raw_score"]="1"; 
    with (out/"risk_assessment.csv").open("w",newline="") as stream: writer=csv.DictWriter(stream,fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
    final=json.loads((out/"route_final.geojson").read_text()); final["properties"]["route_name"]="Z"; (out/"route_final.geojson").write_text(json.dumps(final))
    (out/"emergency_response_plan.md").write_text("L1 L2 L3")
    report=E.evaluate(task/"input",out,task/"reference")
    assert report["components"]["risk_and_selection"]<1 and report["components"]["emergency"]<1
