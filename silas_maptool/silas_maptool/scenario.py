"""Load an ALE scenario (GIS layers) and build strategy-specific occupancy grids.

A *scenario* directory mirrors the ALE ``input/gis/`` folder::

    scenario/
      dem.tif                      terrain elevation (GeoTIFF, any CRS)
      buildings_3d.geojson         building footprints (WGS84 lon/lat)
      airspace_zones.geojson       no-fly / restricted zones (WGS84 lon/lat)
      population_density.tif       optional — used by mission_optimized
      task.json                    optional mission params (start/goal/envelopes)

Everything is projected to a local UTM metric grid at a chosen resolution. The
planner (JPS) consumes a flat, signed-char occupancy array whose layout this module
computes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

from .config import DEFAULT_TASK, normalize_task, profile
from .grid import dilate, utm_epsg

STRATEGIES = ("direct", "conservative", "mission_optimized")

# How aggressively each strategy modifies the grid (defaults; overridable per call).
# cruise_frac sets the cruise altitude as a fraction of the [min,max] AGL envelope;
# a building is an obstacle only where building_height >= cruise_agl - vertical_clearance
# (i.e. buildings shorter than the cruise altitude are overflown — true 3D overflight).
STRATEGY_PARAMS = {
    "direct":        dict(cruise_frac=1.0,  extra_clearance_m=0.0,  pop_block=False),
    "conservative":  dict(cruise_frac=0.35, extra_clearance_m=20.0, pop_block=False),
    "mission_optimized": dict(cruise_frac=0.5, extra_clearance_m=5.0, pop_block=True),
}


def strategy_cruise_agl(task: dict, strategy: str) -> float:
    """Cruise altitude (m AGL) for a strategy, from the task envelope."""
    amin = float(task["constraints"]["altitude_m_agl"]["min"])
    amax = float(task["constraints"]["altitude_m_agl"]["max"])
    frac = STRATEGY_PARAMS.get(strategy, {}).get("cruise_frac", 1.0)
    return amin + frac * (amax - amin)


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


@dataclass
class OccupancyGrid:
    """A JPS-ready occupancy grid: flat signed-char array + origin/dim/resolution."""
    map_data: list           # flat (H*W), int8, 0=free / 1=obstacle (cy*W+cx, y-up)
    dim: list                # [W, H]
    origin: list             # [west, south] metric (bottom-left)
    resolution: float
    shape_northup: tuple     # (H, W) of the source north-up mask (for debugging)


@dataclass
class PlanResult:
    """A planned ALE route."""
    feature: dict            # GeoJSON Feature (geometry + properties), ALE-contract
    metrics: dict            # deterministic distance/duration/energy/n_waypoints
    path_lonlat: list        # [[lon, lat], ...]
    strategy: str
    planning_ms: float


class Scenario:
    def __init__(self, path, grid: GridSpec, dem, building_height, airspace_mask,
                 population, task):
        self.path = Path(path)
        self.grid = grid
        self.dem = dem                          # (H,W) north-up float32 or None
        self.building_height = building_height  # (H,W) north-up float: max building height per cell
        self.buildings_mask = building_height > 0  # backward-compat: all footprints
        self.airspace_mask = airspace_mask      # (H,W) bool north-up
        self.population = population            # (H,W) float or None
        self.task = task
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
        dem_path, bld_path, air_path, pop_path = layer("dem"), layer("buildings"), layer("airspace"), layer("population")
        if not dem_path or not bld_path or not air_path:
            raise FileNotFoundError("task.json layers must resolve dem, buildings, and airspace")
        building_feats = cls._load_features(bld_path)
        airspace_feats = cls._load_features(air_path)

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

        # 4) project polygons to metric CRS; rasterize building heights + airspace
        default_h = float(task["constraints"].get("default_building_height_m", 25.0))
        bld_polys_h = cls._project_geoms_with_height(building_feats, dst_crs, default_h)
        air_polys = cls._project_geoms([f["geometry"] for f in airspace_feats], dst_crs)
        building_height = cls._rasterize_height(bld_polys_h, transform, width, height)
        airspace_mask = cls._rasterize(air_polys, transform, width, height)

        return cls(path, grid, dem, building_height, airspace_mask, population, task)

    # ----------------------------------------------------------- grid building
    def occupancy(self, strategy: str = "direct", *, extra_clearance_m: Optional[float] = None,
                  pop_block: Optional[bool] = None, pop_percentile: Optional[float] = None,
                  terrain_block: bool = False, terrain_ceiling_m: Optional[float] = None,
                  cruise_agl: Optional[float] = None,
                  force_free_lonlat: Optional[list] = None) -> OccupancyGrid:
        """Build a JPS-ready occupancy grid for a strategy.

        Buildings shorter than ``cruise_agl - vertical_clearance`` are overflown
        (3D overflight); only taller buildings and no-fly zones become obstacles.
        """
        if strategy not in STRATEGIES:
            raise ValueError(f"strategy must be one of {STRATEGIES}, got {strategy!r}")
        params = dict(STRATEGY_PARAMS[strategy])
        if extra_clearance_m is not None:
            params["extra_clearance_m"] = extra_clearance_m
        if pop_block is not None:
            params["pop_block"] = pop_block

        cruise = float(cruise_agl) if cruise_agl is not None else strategy_cruise_agl(self.task, strategy)
        vc = float(self.task["constraints"].get("vertical_clearance_m", 10.0))
        thr = cruise - vc
        occ = (self.building_height >= thr) | self.airspace_mask

        if terrain_block and self.dem is not None:
            cap = terrain_ceiling_m
            if cap is None:
                cap = float(np.nanpercentile(self.dem, 99) + 50.0)
            occ = occ | (self.dem > cap)

        if params["pop_block"] and self.population is not None:
            pct = pop_percentile
            if pct is None:
                pct = float(self.task["constraints"].get("noise_sensitive_pop_percentile", 80.0))
            pop = self.population
            thr = float(np.nanpercentile(pop[pop == pop], pct)) if np.isfinite(pop).any() else np.inf
            occ = occ | (pop >= thr)

        radius = int(round(params["extra_clearance_m"] / self.grid.resolution))
        occ = dilate(occ, radius)

        # keep start/goal (and any requested points) free
        for ll in force_free_lonlat or []:
            self._clear_around(occ, ll, radius=max(1, radius, 1))

        # pack for JPS: y-up, origin at bottom-left
        flat = np.flipud(occ).astype(np.int8).reshape(-1)
        return OccupancyGrid(
            map_data=flat.tolist(),
            dim=[self.grid.width, self.grid.height],
            origin=[self.grid.west, self.grid.south],
            resolution=self.grid.resolution,
            shape_northup=(self.grid.height, self.grid.width),
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

    def preview_image(self, strategy: str = "direct", path_lonlat: Optional[list] = None,
                      start: Optional[list] = None, goal: Optional[list] = None) -> Image.Image:
        """Render the (north-up) occupancy grid as a grayscale PIL image."""
        og = self.occupancy(strategy)
        occ_northup = np.flipud(np.array(og.map_data, dtype=np.int8).reshape(self.grid.shape))
        img = np.where(occ_northup > 0, 0, 255).astype(np.uint8)
        rgb = np.stack([img, img, img], axis=-1)
        # overlay DEM shading lightly if present
        if self.dem is not None:
            d = self.dem
            d = np.clip((d - np.nanmin(d)) / (np.nanmax(d) - np.nanmin(d) + 1e-9), 0, 1)
            d = np.nan_to_num(d, nan=0.0)
            rgb = np.clip(rgb.astype(np.int32) - (40 * (1 - d)).astype(np.int32)[..., None], 0, 255).astype(np.uint8)
        pil = Image.fromarray(rgb)
        return pil

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
        data = json.loads(path.read_text())
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
        data = json.loads(path.read_text())
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

    def _clear_around(self, occ: np.ndarray, lonlat, radius: int = 2):
        x, y = self.to_metric(*lonlat)
        c = int((x - self.grid.west) / self.grid.resolution)
        r = int((self.grid.north - y) / self.grid.resolution)
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                rr, cc = r + dr, c + dc
                if 0 <= rr < self.grid.height and 0 <= cc < self.grid.width:
                    occ[rr, cc] = False
