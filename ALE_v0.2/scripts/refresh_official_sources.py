"""Replace fixture DTM/buildings/weather with fixed authoritative snapshots.

Network is used only by this authoring script, never by an ALE agent. Raw API
responses are stored under each task's ``input/source_snapshots`` and subsequent
runs reuse them unless the matching refresh flag is passed. The whole-Hong-Kong
DTM is retained only in the ignored authoring cache; distributed task data is
clipped to ``task.json.planning_extent``. Run
``import_hk_airspace_snapshot.py`` afterwards to restore the hash-pinned RFZ
clip; its redistribution terms remain explicitly pending.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import time
import warnings
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window, from_bounds
from rasterio.warp import transform_bounds
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely.ops import transform as shape_transform

ROOT = Path(__file__).resolve().parents[1]
DTM_URL = "https://www.landsd.gov.hk/landsd_psi_data/SMO/data/Whole_HK_DTM_5m.zip"
BUILDING_QUERY = "https://portal.csdi.gov.hk/server/rest/services/common/landsd_rcd_1637211194312_35158/FeatureServer/0/query"
HKO_WIND = "https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/latest_10min_wind.csv"
CENSUS_QUERY = "https://portal.csdi.gov.hk/server/rest/services/common/censtatd_rcd_1635933193720_58660/FeatureServer/0/query"
USER_AGENT = "ALE-AAM source authoring/0.3"


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(url, path, refresh=False):
    if path.exists() and not refresh: return
    path.parent.mkdir(parents=True,exist_ok=True)
    last=None
    for attempt in range(3):
        try:
            temporary=path.with_suffix(path.suffix+".part")
            request=Request(url,headers={"User-Agent":USER_AGENT,"Accept":"*/*"})
            with urlopen(request,timeout=300) as response, temporary.open("wb") as output:
                while chunk := response.read(1024*1024): output.write(chunk)
            temporary.replace(path); return
        except (HTTPError,URLError,OSError,TimeoutError) as exc:
            last=exc; time.sleep(2**attempt)
    raise RuntimeError(f"download failed after three attempts: {url}: {last}")


def query_json(url,params):
    target=f"{url}?{urlencode(params)}"
    last=None
    for attempt in range(3):
        try:
            request=Request(target,headers={"User-Agent":USER_AGENT,"Accept":"application/json"})
            with urlopen(request,timeout=180) as response:
                data=json.loads(response.read())
            if "error" in data: raise RuntimeError(json.dumps(data["error"],ensure_ascii=False))
            return data
        except (HTTPError,URLError,OSError,TimeoutError,RuntimeError,json.JSONDecodeError) as exc:
            last=exc; time.sleep(2**attempt)
    raise RuntimeError(f"query failed after three attempts: {url}: {last}")


def dtm_source(cache, refresh):
    archive=cache/"Whole_HK_DTM_5m.zip"; fetch(DTM_URL,archive,refresh)
    expanded=cache/"dtm"; expanded.mkdir(parents=True,exist_ok=True)
    if not list(expanded.rglob("*.asc")):
        with zipfile.ZipFile(archive) as bundle: bundle.extractall(expanded)
    files=list(expanded.rglob("*.asc"))
    if len(files)!=1: raise RuntimeError(f"expected one ASC DTM, got {files}")
    return archive,files[0]


def crop_dtm(source,bounds,target):
    to_hk=Transformer.from_crs("EPSG:4326","EPSG:2326",always_xy=True)
    west,south,east,north=bounds
    xs,ys=zip(*(to_hk.transform(x,y) for x,y in ((west,south),(west,north),(east,south),(east,north))))
    with rasterio.open(source) as src:
        window=from_bounds(min(xs),min(ys),max(xs),max(ys),src.transform).round_offsets().round_lengths()
        window=window.intersection(Window(0,0,src.width,src.height))
        window=Window(int(window.col_off),int(window.row_off),int(window.width),int(window.height))
        # Rasterio <= 1.4 sets ndarray.shape internally while reading a
        # window; NumPy 2.5 deprecates that implementation detail.  The
        # resulting array is correct, so silence only this upstream warning.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore",message="Setting the shape on a NumPy array has been deprecated")
            data=src.read(1,window=window,out_dtype="float32")
        transform=src.window_transform(window)
    profile={"driver":"GTiff","height":data.shape[0],"width":data.shape[1],"count":1,"dtype":"float32",
             "crs":"EPSG:2326","transform":transform,"nodata":-9999.0,"compress":"deflate","predictor":3}
    with rasterio.open(target,"w",**profile) as output: output.write(data,1)


def building_snapshot(bounds,path,refresh):
    if path.exists() and not refresh: return json.loads(path.read_text(encoding="utf-8"))
    west,south,east,north=bounds; features=[]; offset=0
    while True:
        params={"where":"1=1","geometry":f"{west},{south},{east},{north}","geometryType":"esriGeometryEnvelope",
                "inSR":4326,"outSR":4326,"spatialRel":"esriSpatialRelIntersects","returnGeometry":"true",
                "outFields":"*","orderByFields":"OBJECTID","resultOffset":offset,"resultRecordCount":3000,"f":"geojson"}
        page=query_json(BUILDING_QUERY,params)
        batch=page.get("features",[]); features.extend(batch)
        if len(batch)<3000: break
        offset+=len(batch)
    for feature in features:
        props=feature.setdefault("properties",{})
        base=float(props.get("BaseHeight") or 0); top=float(props.get("TopHeight") or base)
        props["height_m"]=round(max(0.0,top-base),2)
        props["source"]="Hong Kong LandsD Building FeatureServer"
    features.sort(key=lambda f:int(f.get("properties",{}).get("OBJECTID",0)))
    data={"type":"FeatureCollection","features":features}
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(data,separators=(",",":"),sort_keys=True),encoding="utf-8",newline="\n")
    return data


def census_snapshot(bounds,path,refresh):
    if path.exists() and not refresh: return json.loads(path.read_text(encoding="utf-8"))
    west,south,east,north=bounds
    params={"where":"1=1","geometry":f"{west},{south},{east},{north}","geometryType":"esriGeometryEnvelope",
            "inSR":4326,"outSR":4326,"spatialRel":"esriSpatialRelIntersects","returnGeometry":"true",
            "outFields":"OBJECTID,stpug,t_pop,Shape__Area","orderByFields":"OBJECTID","f":"geojson"}
    data=query_json(CENSUS_QUERY,params)
    data["features"]=sorted(data.get("features",[]),key=lambda f:int(f.get("properties",{}).get("OBJECTID",0)))
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(data,separators=(",",":"),sort_keys=True),encoding="utf-8",newline="\n")
    return data


def write_population(dtm_path,census,target):
    with rasterio.open(dtm_path) as src:
        profile=src.profile.copy(); out_shape=(src.height,src.width); transform=src.transform; crs=src.crs
    project=Transformer.from_crs("EPSG:4326",crs,always_xy=True).transform
    shapes=[]
    for feature in census.get("features",[]):
        props=feature.get("properties",{})
        try:
            population=float(props["t_pop"]); area=float(props["Shape__Area"])
            density=population/max(area/1_000_000,1e-9)
            geometry=shape_transform(project,shape(feature["geometry"]))
            shapes.append((geometry,float(density)))
        except (KeyError,TypeError,ValueError): continue
    data=rasterize(shapes,out_shape=out_shape,transform=transform,fill=0,dtype="float32",all_touched=True)
    profile.update(dtype="float32",count=1,nodata=-9999.0,compress="deflate",predictor=3)
    with rasterio.open(target,"w",**profile) as output: output.write(data,1)


def write_weather(dtm_path,csv_path,target):
    text=csv_path.read_text(encoding="utf-8-sig"); rows=list(csv.DictReader(io.StringIO(text)))
    speeds=[]
    for row in rows:
        try: speeds.append(float(row["10-Minute Mean Speed(km/hour)"])/3.6)
        except (ValueError,TypeError,KeyError): pass
    if not speeds: raise RuntimeError("HKO snapshot has no numeric wind speeds")
    # A spatially constant observed mean is preferable to invented station
    # coordinates; the raw station table remains available for auditing.
    with rasterio.open(dtm_path) as src:
        profile=src.profile.copy(); shape=(src.height,src.width)
    profile.update(dtype="float32",count=1,nodata=-9999.0,compress="deflate",predictor=3)
    with rasterio.open(target,"w",**profile) as output: output.write(np.full(shape,np.mean(speeds),dtype="float32"),1)
    return {"snapshot_time":rows[0].get("Date time"),"station_count":len(speeds),"mean_wind_ms":round(float(np.mean(speeds)),4)}


def update_manifest(task,dtm_archive,building_raw,wind_raw,census_raw,weather_meta,planning_extent):
    manifest_path=task/"input/source_manifest.json"; manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["actual_derivation"]="LandsD 5 m DTM crop, building-height API snapshot, bounded topographic-map snapshot, fixed-date user-provided RFZ snapshot, 2021 Census STPU density raster, and HKO wind snapshot"
    manifest["acquisition_date_utc"]="2026-07-24"
    manifest["crs"]="EPSG:4326 for vectors; EPSG:2326 for authoritative rasters; the tool reprojects with always_xy=True to the mission's local UTM zone"
    manifest["conversion_steps"]=[
        "derive a deterministic 2 km mission-corridor planning extent in EPSG:2326",
        "crop the whole-Hong-Kong LandsD 5 m DTM to the declared planning extent without row reversal",
        "query and clip LandsD buildings to the declared planning extent, then derive height_m as TopHeight minus BaseHeight",
        "query and rasterize 2021 Census STPU persons per square kilometre onto the bounded DTM grid",
        "write the observed HKO station-mean wind speed onto the DTM grid without invented station coordinates",
        "record raw snapshots and SHA-256 for every distributed GIS file",
        "download a bounded, rate-limited LandsD topographic XYZ snapshot for offline visualization",
    ]
    manifest["generated_by"]="scripts/build_tasks.py + scripts/refresh_official_sources.py"
    manifest["planning_extent"]={
        **planning_extent,
        "source_cache":"whole-Hong-Kong authoring sources retained under ignored ALE_v0.2/.source-cache",
        "distributed_scope":"only the bounded, task-specific derived layers are distributed",
    }
    manifest.pop("authoritative_replacement_sources",None)
    manifest["authoritative_sources"]=[
        {"name":"LandsD 5 m DTM","url":"https://data.gov.hk/en-data/dataset/hk-landsd-openmap-5m-grid-dtm","status":"authoritative snapshot crop distributed as gis/dem.tif"},
        {"name":"LandsD building data with height","url":"https://data.gov.hk/en-data/dataset/hk-landsd-openmap-landsd-building","status":"authoritative API snapshot distributed as gis/buildings_3d.geojson"},
        {"name":"CAD/eSUA RFZ fixed-date export","url":"https://esua.cad.gov.hk/web/droneMap","status":"user-provided 2026-07-24 snapshot; source redistribution terms must be confirmed before publication"},
        {"name":"HKO latest ten-minute wind","url":"https://data.gov.hk/en-data/dataset/hk-hko-rss-latest-ten-minute-wind-info","status":"observed snapshot distributed through gis/weather_grid.tif"},
        {"name":"2021 Population Census","url":"https://data.gov.hk/en-data/dataset/hk-censtatd-census_geo-2021-population-census-by-dcd","status":"authoritative STPU snapshot distributed through gis/population_density.tif"},
        {"name":"LandsD topographic map API","url":"https://portal.csdi.gov.hk/csdi-webpage/apidoc/TopographicMapAPI","status":"bounded z12-z17 snapshot distributed through gis/basemaps/hong_kong_landsd.mbtiles"},
    ]
    manifest["layer_provenance"]={
        "dem.tif":{"source":DTM_URL,"source_sha256":digest(dtm_archive),"license":"DATA.GOV.HK terms","crs":"EPSG:2326","status":"authoritative snapshot crop"},
        "buildings_3d.geojson":{"source":BUILDING_QUERY,"raw_sha256":digest(building_raw),"license":"DATA.GOV.HK terms","crs":"EPSG:4326","status":"authoritative API snapshot"},
        "weather_grid.tif":{"source":HKO_WIND,"raw_sha256":digest(wind_raw),"license":"HKO open data terms","crs":"EPSG:2326","details":weather_meta,"status":"observed snapshot; mean station wind raster"},
        "airspace_zones.geojson":{"source":"data/hong_kong_airspace_20260724.zip","source_url":"https://esua.cad.gov.hk/web/droneMap","source_sha256":"b0cde3a908091359c1e10190d185ad74c60511cd943e5498b3c8bdd6b6f16614","snapshot_date":"2026-07-24","crs":"EPSG:4326","license":"Source redistribution terms must be confirmed before benchmark publication","status":"fixed-date user-provided RFZ snapshot; license verification remains a publication blocker"},
        "population_density.tif":{"source":CENSUS_QUERY,"raw_sha256":digest(census_raw),"license":"DATA.GOV.HK terms","crs":"EPSG:2326","status":"2021 Census STPU population per square kilometre"},
    }
    gis=task/"input/gis"
    basemap_manifest=gis/"basemaps/hong_kong_landsd.manifest.json"
    if basemap_manifest.is_file():
        basemap=json.loads(basemap_manifest.read_text(encoding="utf-8"))
        manifest["layer_provenance"]["basemaps/hong_kong_landsd.mbtiles"]={
            "source":basemap["source"]["api_documentation"],
            "license":basemap["source"]["license"],
            "crs":basemap["source"]["crs"],
            "acquisition_date_utc":basemap["acquisition_date_utc"],
            "zoom":[basemap["min_zoom"],basemap["max_zoom"]],
            "status":"authoritative bounded offline visualization snapshot",
        }
    manifest["files"]=[{"path":p.relative_to(gis).as_posix(),"sha256":digest(p)} for p in sorted(gis.rglob("*")) if p.is_file()]
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--cache-dir",type=Path,default=ROOT/".source-cache")
    parser.add_argument("--refresh",action="store_true",help="refresh DTM, vectors, and weather")
    parser.add_argument("--refresh-dtm",action="store_true")
    parser.add_argument("--refresh-vectors",action="store_true")
    parser.add_argument("--refresh-weather",action="store_true")
    args=parser.parse_args(); archive,dtm=dtm_source(args.cache_dir,args.refresh or args.refresh_dtm)
    for task in (p for p in ROOT.iterdir() if p.is_dir() and (p/"input/gis/task.json").exists()):
        cfg=json.loads((task/"input/gis/task.json").read_text(encoding="utf-8"))
        planning_extent=cfg.get("planning_extent") or {}
        bounds=planning_extent.get("bounds_wgs84")
        if not isinstance(bounds,list) or len(bounds)!=4:
            with rasterio.open(task/"input/gis/dem.tif") as old:
                bounds=list(transform_bounds(old.crs,"EPSG:4326",*old.bounds,densify_pts=21))
            planning_extent={"bounds_wgs84":bounds,"corridor_buffer_m":None,
                             "outside_behavior":"visual_basemap_only"}
        snapshots=task/"input/source_snapshots"; snapshots.mkdir(parents=True,exist_ok=True)
        buildings_raw=snapshots/"landsd_buildings_2026-07-24.geojson"
        census_raw=snapshots/"census_2021_stpu.geojson"
        wind_raw=snapshots/"hko_wind_2026-07-24.csv"; fetch(HKO_WIND,wind_raw,args.refresh or args.refresh_weather)
        crop_dtm(dtm,bounds,task/"input/gis/dem.tif")
        buildings=building_snapshot(bounds,buildings_raw,args.refresh or args.refresh_vectors)
        (task/"input/gis/buildings_3d.geojson").write_text(json.dumps(buildings,separators=(",",":"),sort_keys=True),encoding="utf-8",newline="\n")
        census=census_snapshot(bounds,census_raw,args.refresh or args.refresh_vectors)
        write_population(task/"input/gis/dem.tif",census,task/"input/gis/population_density.tif")
        weather_meta=write_weather(task/"input/gis/dem.tif",wind_raw,task/"input/gis/weather_grid.tif")
        update_manifest(task,archive,buildings_raw,wind_raw,census_raw,weather_meta,planning_extent)


if __name__=="__main__": main()
