import json
from pathlib import Path

import pytest

from ale_aam_maptool.config import normalize_task
from ale_aam_maptool.errors import ConfigurationError
from ale_aam_maptool.scenario import Scenario


ROOT = Path(__file__).parents[1]


def test_coordinate_order_and_envelope():
    task = normalize_task(json.loads((ROOT / "sample_scenario/task.json").read_text(encoding="utf-8")))
    assert task["mission"]["start"] == [13.378, 52.5163]
    broken = json.loads((ROOT / "sample_scenario/task.json").read_text(encoding="utf-8"))
    broken["constraints"]["altitude_m_agl"]["max"] = 151
    with pytest.raises(ConfigurationError):
        normalize_task(broken)


def test_route_profile_configuration_is_bounded():
    broken = json.loads((ROOT / "sample_scenario/task.json").read_text(encoding="utf-8"))
    broken["route_profiles"]["C"]["speed_ms"] = 100
    with pytest.raises(ConfigurationError, match="speed_ms"):
        normalize_task(broken)


def test_planning_extent_is_preserved_and_contains_endpoints():
    raw = json.loads((ROOT / "sample_scenario/task.json").read_text(encoding="utf-8"))
    raw["planning_extent"] = {
        "bounds_wgs84": [13.37, 52.51, 13.40, 52.53],
        "corridor_buffer_m": 2000,
        "outside_behavior": "visual_basemap_only",
    }
    task = normalize_task(raw)
    assert task["planning_extent"]["corridor_buffer_m"] == 2000
    raw["planning_extent"]["bounds_wgs84"] = [13.38, 52.51, 13.40, 52.53]
    with pytest.raises(ConfigurationError, match="mission.start is outside planning_extent"):
        normalize_task(raw)


def test_missing_required_layer(tmp_path):
    task = json.loads((ROOT / "sample_scenario/task.json").read_text(encoding="utf-8"))
    (tmp_path / "task.json").write_text(json.dumps(task), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        Scenario.load(tmp_path)


def test_environment_sampling_uses_dem_and_declared_bounds():
    scenario = Scenario.load(ROOT / "sample_scenario")
    start = scenario.task["mission"]["start"]
    result = scenario.environment_at(*start)
    assert result["coordinate"] == pytest.approx(start)
    assert result["rasters"]["terrain_elevation_m_msl"] is not None
    west, south, _, _ = scenario.planning_lonlat_bounds()
    with pytest.raises(ValueError, match="outside planning_extent"):
        scenario.environment_at(west - 0.1, south - 0.1)
