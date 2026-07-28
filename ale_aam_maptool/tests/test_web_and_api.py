import io
import json
import math
import shutil
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from typer.testing import CliRunner

import ale_aam_maptool.basemaps as basemap_module
from ale_aam_maptool.cli import app as cli_app
from ale_aam_maptool.server import app, bind_scenario

ROOT = Path(__file__).parents[1]


def _xyz(lon, lat, zoom):
    x = math.floor((lon + 180) / 360 * (1 << zoom))
    y = math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * (1 << zoom))
    return x, y


def _write_test_mbtiles(path, lon, lat, pack_id="example"):
    image = Image.new("RGB", (8, 8), (31, 119, 140))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    zoom = 14
    x, y = _xyz(lon, lat, zoom)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT);"
            "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB);"
        )
        connection.executemany("INSERT INTO metadata VALUES (?,?)", [
            ("ale_aam_id", pack_id), ("name", "Offline test pack"),
            ("format", "png"), ("minzoom", "14"), ("maxzoom", "14"),
            ("bounds", f"{lon - .01},{lat - .01},{lon + .01},{lat + .01}"),
            ("attribution", "Test data"),
        ])
        connection.execute(
            "INSERT INTO tiles VALUES (?,?,?,?)",
            (zoom, x, (1 << zoom) - 1 - y, buffer.getvalue()),
        )
    return zoom, x, y


def test_final_cli_exposes_manual_tooling_only():
    help_result = CliRunner().invoke(cli_app, ["--help"])
    assert help_result.exit_code == 0
    assert "doctor" in help_result.stdout and "inspect" in help_result.stdout
    assert "validate" in help_result.stdout and "serve" in help_result.stdout
    assert "plan-all" not in help_result.stdout
    assert not any(line.strip().startswith("plan ") for line in help_result.stdout.splitlines())

    doctor = CliRunner().invoke(cli_app, ["doctor", "--json"])
    assert doctor.exit_code == 0
    report = json.loads(doctor.stdout)
    assert report["version"] == "1.0.0"
    assert report["capabilities"] == {
        "automatic_planning": False,
        "geojson_export": True,
        "inspect_environment": True,
        "manual_route_editing": True,
    }


def test_versioned_bound_api_has_no_loader_or_planning_endpoint():
    bind_scenario(ROOT / "sample_scenario")
    client = TestClient(app)
    assert client.get("/v1/health").json()["status"] == "ok"
    summary = client.get("/v1/scenario").json()
    assert len(summary["planning_extent"]["bounds_wgs84"]) == 4
    assert len(summary["planning_extent"]["grid_bounds_wgs84"]) == 4
    layers = client.get("/v1/layers").json()["layers"]
    assert {layer["id"] for layer in layers} == {
        "dem", "buildings", "airspace", "weather", "population", "emergency_sites"
    }
    assert client.get("/v1/layers/airspace/preview").headers["content-type"] == "image/png"
    vector = client.get("/v1/layers/airspace")
    assert vector.status_code == 200 and vector.json()["type"] == "FeatureCollection"
    assert client.get("/v1/layers/dem").status_code == 404
    start = summary["mission"]["start"]
    environment = client.get("/v1/environment", params={"lon": start[0], "lat": start[1]})
    assert environment.status_code == 200
    assert environment.json()["coordinate"] == pytest.approx(start)

    coordinates = [
        start,
        [start[0] + .001, start[1] + .0005],
        [start[0] + .002, start[1] + .001],
        [start[0] + .003, start[1] + .0015],
        summary["mission"]["goal"],
    ]
    feature = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {
            "route_name": "A",
            "waypoints": [
                {"altitude_m_agl": 100, "altitude_m_msl": 120, "speed_ms": 10}
                for _ in coordinates
            ],
        },
    }
    validation = client.post("/v1/validate", json={"feature": feature, "expected_route": "A"})
    assert validation.status_code == 200

    paths = client.get("/openapi.json").json()["paths"]
    assert "/scenario/load" not in paths
    assert "/v1/preview" not in paths
    assert "/v1/plan" not in paths and "/v1/plan-all" not in paths
    assert {"/v1/health", "/v1/scenario", "/v1/layers", "/v1/environment",
            "/v1/validate"} <= set(paths)


def test_declared_planning_extent_is_preserved_and_enforced_by_api(tmp_path):
    scenario_path = tmp_path / "scenario"
    shutil.copytree(ROOT / "sample_scenario", scenario_path)
    task_path = scenario_path / "task.json"
    task = json.loads(task_path.read_text(encoding="utf-8"))
    task["planning_extent"] = {
        "bounds_wgs84": [13.3779, 52.5162, 13.3886, 52.5219],
        "corridor_buffer_m": 2000,
        "outside_behavior": "visual_basemap_only",
    }
    task_path.write_text(json.dumps(task), encoding="utf-8")
    bind_scenario(scenario_path)
    client = TestClient(app)
    summary = client.get("/v1/scenario").json()
    assert summary["planning_extent"]["bounds_wgs84"] == task["planning_extent"]["bounds_wgs84"]
    outside = client.get("/v1/environment", params={"lon": 13.3778, "lat": 52.519})
    assert outside.status_code == 422
    assert "outside planning_extent" in outside.json()["detail"]


def test_basemap_proxy_keeps_credentials_server_side(monkeypatch):
    image = Image.new("RGBA", (4, 4), (34, 92, 120, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    tile_bytes = buffer.getvalue()
    monkeypatch.setenv("ALE_AAM_TIANDITU_TOKEN", "test-tianditu-secret")
    monkeypatch.setenv("ALE_AAM_MAPBOX_TOKEN", "test-mapbox-secret")
    seen_urls = []

    def fake_download(url):
        seen_urls.append(url)
        return tile_bytes, "image/png"

    monkeypatch.setattr(basemap_module, "_download_tile", fake_download)
    basemap_module.tile.cache_clear()
    try:
        client = TestClient(app)
        catalog = client.get("/v1/basemaps").json()
        assert "test-tianditu-secret" not in json.dumps(catalog)
        assert "test-mapbox-secret" not in json.dumps(catalog)
        assert client.get("/v1/basemaps/tianditu-vector/1/1/1.png").status_code == 200
        assert client.get("/v1/basemaps/mapbox-streets/1/1/1.png").status_code == 200
        assert any("mapapi.geodata.gov.hk" in provider.get("attribution", "") or
                   provider["id"] == "hk-landsd-topographic" for provider in catalog["providers"])
    finally:
        basemap_module.tile.cache_clear()


def test_scenario_local_mbtiles_is_discovered_and_served(tmp_path, monkeypatch):
    scenario_path = tmp_path / "scenario"
    shutil.copytree(ROOT / "sample_scenario", scenario_path)
    task = json.loads((scenario_path / "task.json").read_text(encoding="utf-8"))
    lon, lat = task["mission"]["start"]
    zoom, x, y = _write_test_mbtiles(scenario_path / "basemaps" / "example.mbtiles", lon, lat)
    monkeypatch.setenv("ALE_AAM_BASEMAP", "auto")
    bind_scenario(scenario_path)
    client = TestClient(app)
    response = client.get("/v1/basemaps")
    assert response.json()["default"] == "offline-example"
    tile = client.get(f"/v1/basemaps/offline-example/{zoom}/{x}/{y}.png")
    assert tile.status_code == 200 and tile.headers["content-type"] == "image/png"


def test_web_assets_are_offline_and_manual_only():
    web = ROOT / "ale_aam_maptool/web"
    for name in ("index.html", "app.js", "style.css"):
        text = (web / name).read_text(encoding="utf-8")
        text = text.replace("http://www.w3.org/2000/svg", "svg-namespace")
        assert "https://" not in text and "http://" not in text
    index = (web / "index.html").read_text(encoding="utf-8")
    script = (web / "app.js").read_text(encoding="utf-8")
    assert 'src="vendor/leaflet/leaflet.js"' in index
    assert 'id="route-profile"' in index and 'id="auto-plan"' not in index and 'id="plan-all"' not in index
    assert "最终版不提供自动规划" in index
    assert "request('/v1/plan'" not in script and "request('/v1/plan-all'" not in script
    assert "selectManualRoute" in script and "automatic_planning: false" in script
    assert "L.rectangle(state.planningBounds" in script


def test_missing_scenario_is_structured_configuration_error(tmp_path):
    result = CliRunner().invoke(cli_app, ["inspect", "--scenario", str(tmp_path / "missing"), "--json"])
    assert result.exit_code == 2
    error = json.loads(result.stderr.strip().splitlines()[-1])
    assert error["error"]["code"] == "configuration_error"
