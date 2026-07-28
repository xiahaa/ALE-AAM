"""Private constraint grader, staged only by main.evaluate after agent execution."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from pyproj import Geod, Transformer
from shapely.geometry import LineString, shape
from shapely.ops import unary_union

from ale_aam_maptool.scenario import Scenario

GEOD = Geod(ellps="WGS84")
FILES = ("route_a.geojson","route_b.geojson","route_c.geojson","route_final.geojson","risk_assessment.csv","emergency_response_plan.md")
DIMS = ("collision","terrain","population","weather","noise","energy")


def clamp(value): return max(0.0, min(1.0, float(value)))


def distance(a, b): return abs(GEOD.inv(a[0], a[1], b[0], b[1])[2])


def polyline(coords): return sum(distance(a,b) for a,b in zip(coords[:-1],coords[1:]))


def read_json(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return None


def route_checks(feature, route, scenario, rfz):
    checks = []
    if not isinstance(feature, dict) or feature.get("type") != "Feature": return [0.0]*9
    geometry, props = feature.get("geometry",{}), feature.get("properties",{})
    coords = geometry.get("coordinates",[]) if geometry.get("type") == "LineString" else []
    checks.append(float(len(coords)>=5 and all(isinstance(p,list) and len(p)==2 and -180<=p[0]<=180 and -90<=p[1]<=90 for p in coords)))
    start, goal = scenario.task["mission"]["start"], scenario.task["mission"]["goal"]
    checks += [float(bool(coords) and distance(coords[0],start)<=3), float(bool(coords) and distance(coords[-1],goal)<=3)]
    waypoints = props.get("waypoints",[]); checks.append(float(len(waypoints)==len(coords)))
    amin=scenario.task["constraints"]["altitude_m_agl"]["min"]; amax=scenario.task["constraints"]["altitude_m_agl"]["max"]
    smin=scenario.task["constraints"]["speed_ms"]["min"]; smax=scenario.task["constraints"]["speed_ms"]["max"]
    checks.append(float(bool(waypoints) and all(amin<=w.get("altitude_m_agl",-1)<=amax and smin<=w.get("speed_ms",-1)<=smax and "altitude_m_msl" in w for w in waypoints)))
    checks.append(float(props.get("route_name")==route and props.get("objective")==scenario.task["route_profiles"][route]["objective"]))
    energy=float(props.get("estimated_energy_wh",-1)); capacity=float(scenario.task["aircraft"].get("battery_capacity_wh",0))
    checks.append(float(0 <= energy <= capacity))
    line = LineString(coords) if len(coords)>=2 else None
    checks.append(float(line is not None and (rfz.is_empty or not line.intersects(rfz))))
    clearance = float(scenario.task["constraints"]["vertical_clearance_m"])
    safe=[]
    for coord,w in zip(coords[1:-1],waypoints[1:-1]): safe.append(float(w.get("altitude_m_agl",-1)) >= scenario._sample_northup(scenario.building_height,coord)+clearance)
    # Start/goal can be authorized rooftop pads; assess en-route clearance.
    checks.append(float(all(safe)))
    return checks


def recompute_risk(feature, scenario, rfz):
    coords=feature["geometry"]["coordinates"]; props=feature.get("properties",{}); waypoints=props.get("waypoints",[])
    popmax=float(np.nanmax(scenario.population)) if scenario.population is not None and np.isfinite(scenario.population).any() else 1.0
    pops=[max(0,scenario.pop_at(p)) for p in coords if math.isfinite(scenario.pop_at(p))]
    pop=clamp((sum(pops)/max(1,len(pops)))/max(1,popmax))
    terrain=[scenario.dem_at(p) for p in coords if math.isfinite(scenario.dem_at(p))]
    terrain_score=clamp((max(terrain)-min(terrain))/100 if terrain else 0)
    line=LineString(coords); rfz_hit=0 if rfz.is_empty or not line.intersects(rfz) else 1
    clearance=float(scenario.task["constraints"]["vertical_clearance_m"])
    deficits=[]
    for p,w in zip(coords,waypoints): deficits.append(clamp((scenario._sample_northup(scenario.building_height,p)+clearance-float(w.get("altitude_m_agl",0)))/50))
    collision=clamp(max([rfz_hit,*deficits],default=0))
    weather_path=scenario.path/scenario.task["layers"]["weather"]
    weather=0.3
    if weather_path.exists():
        import rasterio
        with rasterio.open(weather_path) as src:
            transformer=Transformer.from_crs("EPSG:4326",src.crs,always_xy=True)
            samples=[]
            for coord in coords:
                x,y=transformer.transform(*coord); value=float(next(src.sample([(x,y)]))[0])
                if math.isfinite(value) and (src.nodata is None or value != src.nodata): samples.append(value)
        weather=clamp(sum(samples)/max(1,len(samples))/15) if samples else 0.3
    speeds=[float(w.get("speed_ms",0)) for w in waypoints]
    speed=sum(speeds)/max(1,len(speeds))
    dist=polyline(coords); duration=dist/max(speed,0.1)
    energy=float(scenario.task["aircraft"].get("cruise_power_w",650))*duration*1.2/3600
    capacity=float(scenario.task["aircraft"].get("battery_capacity_wh",2200))
    return {"collision":collision,"terrain":terrain_score,"population":pop,"weather":weather,
            "noise":clamp(pop*(.5+.5*speed/18)),"energy":clamp(energy/capacity)}


def evaluate(input_dir, output_dir, reference_dir):
    input_dir,output_dir,reference_dir=map(Path,(input_dir,output_dir,reference_dir))
    anchors=read_json(reference_dir/"anchors.json") or {}
    weights=anchors.get("risk_weights",dict(zip(DIMS,(.3,.1,.2,.15,.1,.15))))
    present={name:(output_dir/name).is_file() and (output_dir/name).stat().st_size>0 for name in FILES}
    file_score=sum(present.values())/len(FILES)
    scenario=Scenario.load(input_dir/"gis")
    air=read_json(input_dir/"gis"/"airspace_zones.geojson") or {"features":[]}
    rfz=unary_union([shape(f["geometry"]) for f in air.get("features",[])])
    features={route:read_json(output_dir/f"route_{route.lower()}.geojson") for route in "ABC"}
    route_values=[]; risks={}; route_check_report={}
    for route,feature in features.items():
        values=route_checks(feature,route,scenario,rfz) if feature else [0.0]*9
        route_check_report[route]=values
        route_values.extend(values)
        if feature and sum(values[:5])>=4: 
            try: risks[route]=recompute_risk(feature,scenario,rfz)
            except Exception: pass
    distinct=0.0
    signatures=[]
    for feature in features.values():
        if not feature: continue
        props=feature.get("properties",{}); waypoints=props.get("waypoints",[])
        signatures.append(json.dumps({"coordinates":feature.get("geometry",{}).get("coordinates",[]),
                                      "objective":props.get("objective"),
                                      "agl":[w.get("altitude_m_agl") for w in waypoints],
                                      "speed":[w.get("speed_ms") for w in waypoints]},sort_keys=True))
    if len(signatures)==3: distinct=len(set(signatures))/3
    profile_score=(sum(route_values)/max(1,len(route_values))*.9+distinct*.1)

    rows=[]
    if present["risk_assessment.csv"]:
        try:
            with (output_dir/"risk_assessment.csv").open(encoding="utf-8-sig",newline="") as stream: rows=list(csv.DictReader(stream))
        except Exception: rows=[]
    risk_points=[]
    tolerance=float(anchors.get("tolerances",{}).get("risk_raw",.15))
    totals={}
    for route in "ABC":
        submitted_total=0.0
        route_rows=[r for r in rows if r.get("route","").upper()==route]
        for dim in DIMS:
            matching=[r for r in route_rows if r.get("dimension","").lower()==dim]
            try:
                row=matching[0]; raw=float(row["raw_score"]); weight=float(row["weight"]); weighted=float(row["weighted_score"])
                expected=risks[route][dim]
                risk_points += [float(abs(raw-expected)<=tolerance),float(abs(weight-weights[dim])<=.001),float(abs(weighted-raw*weight)<=.01)]
                submitted_total+=weighted
            except Exception: risk_points += [0,0,0]
        total_rows=[r for r in route_rows if r.get("dimension","").upper()=="TOTAL"]
        try:
            total=float(total_rows[0]["total_score"]); totals[route]=total
            risk_points.append(float(abs(total-submitted_total)<=.01))
        except Exception: risk_points.append(0)
    risk_points.append(float(len(rows)==21))
    final=read_json(output_dir/"route_final.geojson")
    final_name=final.get("properties",{}).get("route_name") if final else None
    final_match=float(final_name in features and final and features.get(final_name) and final.get("geometry")==features[final_name].get("geometry"))
    expected_totals={r:sum(risks[r][d]*weights[d] for d in DIMS) for r in risks}
    best=min(expected_totals,key=expected_totals.get) if expected_totals else None
    selection=float(bool(final_name==best and totals and min(totals,key=totals.get)==final_name))
    risk_score=(sum(risk_points)/max(1,len(risk_points))*.8+final_match*.1+selection*.1)

    text=(output_dir/"emergency_response_plan.md").read_text(encoding="utf-8",errors="ignore").lower() if present["emergency_response_plan.md"] else ""
    terms=["l1","l2","l3","fault","trigger","communication","recovery","report"]
    sites=anchors.get("verified_emergency_sites",[]); special=anchors.get("required_emergency_terms",[])
    emergency_points=[float(term.lower() in text) for term in terms+sites+special]
    emergency_score=sum(emergency_points)/max(1,len(emergency_points))
    components={"files_schema":file_score,"route_constraints_profiles":profile_score,"risk_and_selection":risk_score,"emergency":emergency_score}
    score=clamp(.10*file_score+.35*profile_score+.35*risk_score+.20*emergency_score)
    return {"score":round(score,6),"components":{k:round(v,6) for k,v in components.items()},"diagnostics":{"present":present,"rows":len(rows),"risks":risks,"route_checks":route_check_report,"selected":final_name,"expected_best":best}}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--input",required=True); parser.add_argument("--output",required=True); parser.add_argument("--reference",required=True)
    args=parser.parse_args()
    try: report=evaluate(args.input,args.output,args.reference)
    except Exception as exc: report={"score":0.0,"components":{},"diagnostics":{"evaluator_error":str(exc)}}
    print(json.dumps(report,separators=(",",":"),sort_keys=True))


if __name__=="__main__": main()
