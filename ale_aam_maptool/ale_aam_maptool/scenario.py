"""Load and query the GIS layers in an ALE-AAM scenario.

A *scenario* directory mirrors the ALE ``input/gis/`` folder::

    scenario/
      dem.tif                      terrain elevation (GeoTIFF, any CRS)
      buildings_3d.geojson         building footprints (WGS84 lon/lat)
      airspace_zones.geojson       no-fly / restricted zones (WGS84 lon/lat)
      population_density.tif       optional — used by mission_optimized
      task.json                    optional mission params (start/goal/envelopes)

Everything is projected to a local UTM metric grid at a chosen resolution for
deterministic layer sampling and visualization. Automatic route planning is not
part of the final public tool.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import rasterio
from PIL import Image, ImageDraw
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from shapely.geometry import Point, shape
from shapely.ops import transform as shp_transform

from .config import normalize_task
from .grid import utm_epsg


@dataclass
class GridSpec:
    transform: Affine       # rasterio north-up transform (col,row)->metric(x,y)
    width: int
    height: int
    crs: CRS                # metric CRS (UTM EPSG)
    resolution: float
    west: float
    south: float
    east: float
    north: float

    @property
    def shape(self):
        return (self.height, self.width)


class Scenario:
    def __init__(self, path, grid: GridSpec, dem, building_height, airspace_mask,
                 population, task, weather=None, layer_paths=None, vector_features=None):
        self.path = Path(path)
        self.grid = grid
        self.dem = dem                          # (H,W) north-up float32 or None
        self.building_height = building_height  # (H,W) north-up float: max building height per cell
        self.buildings_mask = building_height > 0  # backward-compat: all footprints
        self.airspace_mask = airspace_mask      # (H,W) bool north-up
        self.population = population            # (H,W) float or None
        self.weather = weather                  # (H,W) float or None
        self.task = task
        self.layer_paths = layer_paths or {}
        self.vector_features = vector_features or {
            "buildings": [], "airspace": [], "emergency_sites": [],
        }
        self._layer_image_cache = {}
        # cached coordinate transformers (4326 <-> metric CRS)
        self._to_metric = Transformer.from_crs("EPSG:4326", grid.crs, always_xy=True)
        self._to_lonlat = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True)

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, path, resolution: float = 5.0) -> "Scenario":
        path = Path(path)
        task_path = path / "task.json"
        if not task_path.exists():
            raise FileNotFoundError(f"missing required scenario file: {task_path}")
        task = normalize_task(json.loads(task_path.read_text(encoding="utf-8")))
        layers = task["layers"]
        def layer(key):
            name = layers.get(key)
            candidate = path / name if name else None
            return candidate if candidate and candidate.exists() else None
        layer_paths = {key: layer(key) for key in
                       ("dem", "buildings", "airspace", "population", "weather", "emergency_sites")}
        dem_path = layer_paths["dem"]
        bld_path = layer_paths["buildings"]
        air_path = layer_paths["airspace"]
        pop_path = layer_paths["population"]
        weather_path = layer_paths["weather"]
        if not dem_path or not bld_path or not air_path:
            raise FileNotFoundError("task.json layers must resolve dem, buildings, and airspace")
        building_feats = cls._load_features(bld_path)
        airspace_feats = cls._load_features(air_path)
        emergency_feats = cls._load_features(layer_paths["emergency_sites"])

        all_geoms = [f["geometry"] for f in building_feats + airspace_feats]
        # 1) lon/lat extent + UTM CRS (prefer DEM bounds; else geometry bounds)
        if dem_path:
            with rasterio.open(dem_path) as src:
                west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        else:
            west, south, east, north = cls._geom_bounds_lonlat(all_geoms)
        epsg = utm_epsg((west + east) / 2, (south + north) / 2)
        dst_crs = CRS.from_epsg(epsg)

        # 2) metric bounds (pad ~2 cells)
        pad = resolution * 2
        proj = Transformer.from_crs("EPSG:4326", dst_crs, always_xy=True)
        corners = [proj.transform(*p) for p in
                   [(west, south), (west, north), (east, south), (east, north)]]
        xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
        west_m, east_m = min(xs) - pad, max(xs) + pad
        south_m, north_m = min(ys) - pad, max(ys) + pad
        width = max(1, int(np.ceil((east_m - west_m) / resolution)))
        height = max(1, int(np.ceil((north_m - south_m) / resolution)))
        transform = from_origin(west_m, north_m, resolution, resolution)
        grid = GridSpec(transform, width, height, dst_crs, resolution,
                        west_m, south_m, east_m, north_m)

        # 3) reproject DEM + population onto this grid (north-up)
        dem = cls._reproject_raster(dem_path, transform, width, height, dst_crs) if dem_path else None
        population = cls._reproject_raster(pop_path, transform, width, height, dst_crs) if pop_path else None
        weather = cls._reproject_raster(weather_path, transform, width, height, dst_crs) if weather_path else None

        # 4) project polygons to metric CRS; rasterize building heights + airspace
        default_h = float(task["constraints"].get("default_building_height_m", 25.0))
        bld_polys_h = cls._project_geoms_with_height(building_feats, dst_crs, default_h)
        air_polys = cls._project_geoms([f["geometry"] for f in airspace_feats], dst_crs)
        building_height = cls._rasterize_height(bld_polys_h, transform, width, height)
        airspace_mask = cls._rasterize(air_polys, transform, width, height)

        return cls(
            path, grid, dem, building_height, airspace_mask, population, task,
            weather=weather, layer_paths=layer_paths,
            vector_features={"buildings": building_feats, "airspace": airspace_feats,
                             "emergency_sites": emergency_feats},
        )

    # ----------------------------------------------------------- coordinates
    def to_metric(self, lon, lat):
        return self._to_metric.transform(lon, lat)

    def to_lonlat(self, x, y):
        return self._to_lonlat.transform(x, y)

    def lonlat_bounds(self):
        """Return (west, south, east, north) of the metric grid in lon/lat."""
        corners = [(self.grid.west, self.grid.south), (self.grid.east, self.grid.south),
                   (self.grid.east, self.grid.north), (self.grid.west, self.grid.north)]
        lons, lats = [], []
        for x, y in corners:
            lo, la = self.to_lonlat(x, y)
            lons.append(lo); lats.append(la)
        return min(lons), min(lats), max(lons), max(lats)

    def planning_lonlat_bounds(self):
        """Return the declared planning boundary, or the grid boundary for legacy tasks."""
        extent = self.task.get("planning_extent")
        if isinstance(extent, dict) and extent.get("bounds_wgs84"):
            return tuple(map(float, extent["bounds_wgs84"]))
        return self.lonlat_bounds()

    def _sample_northup(self, arr, lonlat):
        if arr is None:
            return float("nan")
        x, y = self.to_metric(*lonlat)
        c = int((x - self.grid.west) / self.grid.resolution)
        r = int((self.grid.north - y) / self.grid.resolution)
        if 0 <= r < self.grid.height and 0 <= c < self.grid.width:
            v = arr[r, c]
            return float(v) if np.isfinite(v) else float("nan")
        return float("nan")

    def pop_at(self, lonlat) -> float:
        return self._sample_northup(self.population, lonlat)

    def dem_at(self, lonlat) -> float:
        return self._sample_northup(self.dem, lonlat)

    def weather_at(self, lonlat) -> float:
        return self._sample_northup(self.weather, lonlat)

    @staticmethod
    def _finite_or_none(value):
        return round(float(value), 3) if np.isfinite(value) else None

    def layer_catalog(self) -> list[dict]:
        """Describe browser-visible layers without exposing server file paths."""
        definitions = (
            ("dem", "地形高程", "raster", "m MSL", self.dem is not None),
            ("buildings", "3D 建筑", "vector", "m", bool(self.vector_features["buildings"])),
            ("airspace", "空域管制区", "vector", None, bool(self.vector_features["airspace"])),
            ("weather", "气象网格", "raster", "m/s", self.weather is not None),
            ("population", "人口密度", "raster", "people/km²", self.population is not None),
            ("emergency_sites", "应急起降点", "vector", None, bool(self.vector_features["emergency_sites"])),
        )
        return [
            {"id": key, "name": name, "kind": kind, "unit": unit,
             "available": bool(available), "preview_url": f"/v1/layers/{key}/preview"}
            for key, name, kind, unit, available in definitions
        ]

    def vector_layer(self, layer_id: str) -> dict:
        """Return one declared vector layer as GeoJSON without exposing a path."""
        if layer_id not in self.vector_features:
            raise KeyError(layer_id)
        return {"type": "FeatureCollection", "features": self.vector_features[layer_id]}

    def environment_at(self, lon: float, lat: float) -> dict:
        """Return raster samples and visible vector properties at a WGS84 point."""
        west, south, east, north = self.planning_lonlat_bounds()
        if not (west <= lon <= east and south <= lat <= north):
            raise ValueError(
                "coordinate is outside planning_extent; only basemap visualization is available"
            )
        point = Point(lon, lat)
        hits = {}
        for key, features in self.vector_features.items():
            matched = []
            for feature in features:
                try:
                    geometry = shape(feature["geometry"])
                    is_hit = geometry.covers(point)
                    if geometry.geom_type in ("Point", "MultiPoint"):
                        is_hit = geometry.distance(point) <= 0.00035
                except Exception:
                    continue
                if is_hit:
                    props = dict(feature.get("properties") or {})
                    if key == "buildings":
                        props.setdefault("height_m", self._feature_height(props, 0.0))
                    matched.append(props)
                if len(matched) >= 8:
                    break
            hits[key] = matched
        return {
            "coordinate": [round(float(lon), 7), round(float(lat), 7)],
            "rasters": {
                "terrain_elevation_m_msl": self._finite_or_none(self.dem_at((lon, lat))),
                "weather_value": self._finite_or_none(self.weather_at((lon, lat))),
                "population_density": self._finite_or_none(self.pop_at((lon, lat))),
            },
            "features": hits,
        }

    @staticmethod
    def _normalized(arr):
        finite = np.isfinite(arr)
        if not finite.any():
            return np.zeros(arr.shape, dtype=np.float32), finite
        values = arr[finite]
        low, high = np.nanpercentile(values, (2, 98))
        if high <= low:
            high = low + 1.0
        return np.clip((arr - low) / (high - low), 0, 1), finite

    def layer_preview_image(self, layer_id: str) -> Image.Image:
        """Render a deterministic, transparent PNG for one scenario layer."""
        if layer_id in self._layer_image_cache:
            return self._layer_image_cache[layer_id].copy()
        height, width = self.grid.shape
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        if layer_id == "dem" and self.dem is not None:
            norm, finite = self._normalized(self.dem)
            rgba[..., 0] = (44 + 130 * norm).astype(np.uint8)
            rgba[..., 1] = (83 + 95 * norm).astype(np.uint8)
            rgba[..., 2] = (73 + 72 * norm).astype(np.uint8)
            rgba[..., 3] = np.where(finite, 255, 0).astype(np.uint8)
        elif layer_id == "buildings":
            rgba[self.buildings_mask] = (245, 158, 11, 210)
        elif layer_id == "airspace":
            rgba[self.airspace_mask] = (239, 68, 68, 175)
        elif layer_id == "population" and self.population is not None:
            norm, finite = self._normalized(self.population)
            rgba[..., 0], rgba[..., 1], rgba[..., 2] = 249, 115, 22
            rgba[..., 3] = np.where(finite, 25 + norm * 185, 0).astype(np.uint8)
        elif layer_id == "weather" and self.weather is not None:
            norm, finite = self._normalized(self.weather)
            rgba[..., 0] = (14 + 40 * norm).astype(np.uint8)
            rgba[..., 1] = (116 + 90 * norm).astype(np.uint8)
            rgba[..., 2] = (205 + 45 * norm).astype(np.uint8)
            rgba[..., 3] = np.where(finite, 30 + norm * 175, 0).astype(np.uint8)
        elif layer_id == "emergency_sites":
            image = Image.fromarray(rgba)
            draw = ImageDraw.Draw(image)
            for feature in self.vector_features["emergency_sites"]:
                try:
                    geom = shape(feature["geometry"])
                    points = list(geom.geoms) if geom.geom_type == "MultiPoint" else [geom]
                    for point in points:
                        x, y = self.to_metric(point.x, point.y)
                        col = (x - self.grid.west) / self.grid.resolution
                        row = (self.grid.north - y) / self.grid.resolution
                        draw.ellipse((col - 5, row - 5, col + 5, row + 5),
                                     fill=(250, 204, 21, 255), outline=(24, 24, 27, 255), width=1)
                except Exception:
                    continue
            self._layer_image_cache[layer_id] = image
            return image.copy()
        else:
            known = {layer["id"] for layer in self.layer_catalog()}
            if layer_id not in known:
                raise KeyError(layer_id)
        image = Image.fromarray(rgba)
        self._layer_image_cache[layer_id] = image
        return image.copy()

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _find(dir_: Path, stem: str, suffix: str) -> Optional[Path]:
        for cand in (dir_ / f"{stem}{suffix}", dir_ / f"{stem}.json" if suffix == ".geojson" else None):
            if cand and cand.exists():
                return cand
        # case-insensitive fallback
        for p in dir_.glob("*"):
            if p.stem.lower() == stem.lower() and p.suffix.lower() == suffix:
                return p
        return None

    @staticmethod
    def _load_geojson(path: Path) -> list:
        data = json.loads(path.read_text(encoding="utf-8"))
        feats = data.get("features") if isinstance(data, dict) else data
        if feats is None:                       # bare geometry
            feats = [data] if isinstance(data, dict) else []
        geoms = []
        for f in feats:
            g = f.get("geometry", f) if isinstance(f, dict) else None
            if g and g.get("type"):
                geoms.append(g)
        return geoms

    @staticmethod
    def _load_features(path: Path) -> list:
        """Return feature dicts (geometry + properties), handling FC/Feature/geometry."""
        if path is None:
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            feats = data.get("features", [])
        elif isinstance(data, dict) and data.get("type") == "Feature":
            feats = [data]
        elif isinstance(data, dict) and data.get("geometry") is None and "type" in data:
            feats = [{"type": "Feature", "geometry": data, "properties": {}}]  # bare geometry
        else:
            feats = data if isinstance(data, list) else []
        return [f for f in feats if isinstance(f, dict) and f.get("geometry", {}).get("type")]

    @staticmethod
    def _feature_height(props: dict, default_h: float) -> float:
        for key in ("height_m", "height"):
            v = props.get(key)
            if v not in (None, ""):
                try:
                    return max(0.0, float(v))
                except (TypeError, ValueError):
                    pass
        lv = props.get("building:levels") or props.get("levels")
        if lv not in (None, ""):
            try:
                return max(0.0, float(lv) * 3.5)
            except (TypeError, ValueError):
                pass
        return float(default_h)

    @staticmethod
    def _geom_bounds_lonlat(geoms) -> tuple:
        from shapely.geometry import shape as _shape
        xs, ys = [], []
        for g in geoms:
            minx, miny, maxx, maxy = _shape(g).bounds
            xs += [minx, maxx]; ys += [miny, maxy]
        if not xs:
            raise ValueError("scenario has neither a DEM extent nor vector geometry")
        return min(xs), min(ys), max(xs), max(ys)

    @staticmethod
    def _project_geoms(geoms, dst_crs):
        t = Transformer.from_crs("EPSG:4326", dst_crs, always_xy=True).transform
        out = []
        for g in geoms:
            try:
                out.append(shp_transform(t, shape(g)))
            except Exception:
                continue
        return out

    @classmethod
    def _project_geoms_with_height(cls, features, dst_crs, default_h):
        """Project building features to metric CRS, returning [(shapely, height_m), ...]."""
        t = Transformer.from_crs("EPSG:4326", dst_crs, always_xy=True).transform
        out = []
        for f in features:
            try:
                g = shp_transform(t, shape(f["geometry"]))
            except Exception:
                continue
            h = cls._feature_height(f.get("properties", {}), default_h)
            out.append((g, h))
        return out

    @staticmethod
    def _rasterize(polys, transform, width, height) -> np.ndarray:
        if not polys:
            return np.zeros((height, width), dtype=bool)
        shapes = [(g.buffer(0), 1) for g in polys if not g.is_empty]
        arr = rasterize(shapes, out_shape=(height, width), transform=transform,
                        fill=0, dtype="uint8", all_touched=True)
        return arr.astype(bool)

    @staticmethod
    def _rasterize_height(polys_height, transform, width, height) -> np.ndarray:
        """Max building height per cell. Sorted ascending so taller overwrites shorter."""
        if not polys_height:
            return np.zeros((height, width), dtype=np.float32)
        shapes = sorted([(g.buffer(0), h) for g, h in polys_height if not g.is_empty],
                        key=lambda x: x[1])
        arr = rasterize(shapes, out_shape=(height, width), transform=transform,
                        fill=0, dtype="float32", all_touched=True)
        return arr.astype(np.float32)

    @staticmethod
    def _reproject_raster(path, transform, width, height, dst_crs,
                          resampling=Resampling.bilinear) -> np.ndarray:
        with rasterio.open(path) as src:
            out = np.full((height, width), np.nan, dtype=np.float32)
            reproject(source=rasterio.band(src, 1), destination=out,
                      src_transform=src.transform, src_crs=src.crs,
                      dst_transform=transform, dst_crs=dst_crs, resampling=resampling,
                      src_nodata=src.nodata, dst_nodata=np.nan)
            return out
