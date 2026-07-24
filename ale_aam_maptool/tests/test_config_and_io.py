import json
from pathlib import Path

import numpy as np
import pytest
from rasterio.crs import CRS
from rasterio.transform import from_origin

from ale_aam_maptool.config import normalize_task
from ale_aam_maptool.errors import ConfigurationError
from ale_aam_maptool.geojson_out import write_json_atomic
from ale_aam_maptool.metrics import build_waypoints
from ale_aam_maptool.scenario import GridSpec, Scenario


ROOT = Path(__file__).parents[1]


def test_coordinate_order_and_envelope():
    task = normalize_task(json.loads((ROOT / "sample_scenario/task.json").read_text(encoding="utf-8")))
    assert task["mission"]["start"] == [13.378, 52.5163]
    broken = json.loads((ROOT / "sample_scenario/task.json").read_text(encoding="utf-8"))
    broken["constraints"]["altitude_m_agl"]["max"] = 151
    with pytest.raises(ConfigurationError): normalize_task(broken)


def test_route_profile_configuration_is_bounded():
    broken = json.loads((ROOT / "sample_scenario/task.json").read_text(encoding="utf-8"))
    broken["route_profiles"]["C"]["speed_ms"] = 100
    with pytest.raises(ConfigurationError, match="speed_ms"):
        normalize_task(broken)


def test_missing_required_layer(tmp_path):
    task = json.loads((ROOT / "sample_scenario/task.json").read_text(encoding="utf-8"))
    (tmp_path / "task.json").write_text(json.dumps(task), encoding="utf-8")
    with pytest.raises(FileNotFoundError): Scenario.load(tmp_path)


def test_atomic_json_output(tmp_path):
    target = tmp_path / "nested/route.geojson"
    write_json_atomic({"longitude_first": [114.1, 22.3]}, target)
    assert json.loads(target.read_text(encoding="utf-8"))["longitude_first"] == [114.1, 22.3]
    assert not list(target.parent.glob("*.tmp"))


def _array_scenario():
    task = normalize_task(json.loads((ROOT / "sample_scenario/task.json").read_text(encoding="utf-8")))
    grid = GridSpec(from_origin(0, 5, 1, 1), 5, 5, CRS.from_epsg(4326), 1, 0, 0, 5, 5)
    dem = np.full((5, 5), 12.0, dtype=np.float32)
    buildings = np.zeros((5, 5), dtype=np.float32)
    buildings[0, 0] = 100.0
    airspace = np.zeros((5, 5), dtype=bool)
    airspace[2, 2] = True
    return Scenario(ROOT, grid, dem, buildings, airspace, None, task)


def test_building_height_and_rfz_clearance_buffer():
    scenario = _array_scenario()
    high = np.flipud(np.array(scenario.occupancy("direct", cruise_agl=145, extra_clearance_m=0).map_data).reshape(5, 5))
    low = np.flipud(np.array(scenario.occupancy("direct", cruise_agl=100, extra_clearance_m=0).map_data).reshape(5, 5))
    assert not high[0, 0] and low[0, 0]
    buffered = np.flipud(np.array(scenario.occupancy("direct", cruise_agl=145, extra_clearance_m=1).map_data).reshape(5, 5))
    assert buffered[1:4, 1:4].all()


def test_dem_contributes_to_msl_altitude():
    scenario = _array_scenario()
    profile = {"cruise_agl_m": 100, "speed_ms": 10}
    waypoints = build_waypoints([[2.5, 2.5], [3.5, 2.5]], profile, scenario)
    assert waypoints[0]["altitude_m_agl"] == 100.0
    assert waypoints[0]["altitude_m_msl"] == 112.0
