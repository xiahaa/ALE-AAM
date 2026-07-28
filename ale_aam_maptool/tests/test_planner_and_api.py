import json
import io
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
from ale_aam_maptool.errors import NoFeasiblePathError
from ale_aam_maptool.planner import plan_all_routes, plan_route
from ale_aam_maptool.scenario import Scenario
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
        connection.execute("INSERT INTO tiles VALUES (?,?,?,?)",
                           (zoom, x, (1 << zoom) - 1 - y, buffer.getvalue()))
    return zoom, x, y


def test_plan_all_schema_and_determinism(tmp_path):
    scenario = Scenario.load(ROOT / "sample_scenario")
    first, second = plan_all_routes(scenario), plan_all_routes(scenario)
    for route in "ABC":
        assert first[route].feature["geometry"] == second[route].feature["geometry"]
        assert first[route].feature["properties"]["waypoints"] == second[route].feature["properties"]["waypoints"]
        assert all("altitude_m_msl" in w for w in first[route].feature["properties"]["waypoints"])


def test_no_path_has_structured_error(monkeypatch):
    scenario = Scenario.load(ROOT / "sample_scenario")
    monkeypatch.setattr("ale_aam_maptool.planner._native_plan", lambda *args: ([], 0.0, "blocked"))
    with pytest.raises(NoFeasiblePathError): plan_route(scenario, "A")


def test_versioned_bound_api_has_no_path_loader():
    bind_scenario(ROOT / "sample_scenario")
    client = TestClient(app)
    assert client.get("/v1/health").json()["status"] == "ok"
    assert client.get("/v1/scenario").status_code == 200
    assert client.get("/v1/preview").headers["content-type"] == "image/png"
    layers = client.get("/v1/layers").json()["layers"]
    assert {layer["id"] for layer in layers} == {
        "dem", "buildings", "airspace", "weather", "population", "emergency_sites"
    }
    assert client.get("/v1/layers/airspace/preview").headers["content-type"] == "image/png"
    vector = client.get("/v1/layers/airspace")
    assert vector.status_code == 200
    assert vector.json()["type"] == "FeatureCollection"
    assert len(vector.json()["features"]) == 1
    assert client.get("/v1/layers/dem").status_code == 404
    buildings = client.get("/v1/layers/buildings", headers={"Accept-Encoding": "gzip"})
    assert buildings.status_code == 200
    assert buildings.headers.get("content-encoding") == "gzip"
    start = client.get("/v1/scenario").json()["mission"]["start"]
    environment = client.get("/v1/environment", params={"lon": start[0], "lat": start[1]})
    assert environment.status_code == 200
    assert environment.json()["coordinate"] == pytest.approx(start)
    basemaps = client.get("/v1/basemaps")
    assert basemaps.status_code == 200
    assert any(provider["id"] == "offline" for provider in basemaps.json()["providers"])
    landsd = next(provider for provider in basemaps.json()["providers"]
                  if provider["id"] == "hk-landsd-topographic")
    assert landsd["available"] is True
    assert landsd["min_zoom"] == 10 and landsd["max_zoom"] == 20
    assert "token" not in basemaps.text.lower()
    assert "access_token" not in basemaps.text.lower()
    planned = client.post("/v1/plan", json={"route": "A", "densify_interval_m": 200})
    assert planned.status_code == 200
    assert planned.json()["feature"]["properties"]["route_name"] == "A"
    assert planned.json()["metrics"]["n_waypoints"] >= 5
    planned_all = client.post("/v1/plan-all")
    assert planned_all.status_code == 200
    assert set(planned_all.json()) == {"A", "B", "C"}
    paths = client.get("/openapi.json").json()["paths"]
    assert "/scenario/load" not in paths
    assert set(("/v1/health","/v1/scenario","/v1/preview","/v1/layers",
                "/v1/layers/{layer_id}/preview", "/v1/layers/{layer_id}", "/v1/environment",
                "/v1/basemaps", "/v1/basemaps/{provider_id}/{z}/{x}/{y}.png",
                "/v1/plan","/v1/plan-all","/v1/validate")) <= set(paths)


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
        assert {item["id"] for item in catalog["providers"] if item["available"]} >= {
            "offline", "hk-landsd-topographic", "tianditu-vector", "mapbox-streets"
        }
        assert "test-tianditu-secret" not in json.dumps(catalog)
        assert "test-mapbox-secret" not in json.dumps(catalog)
        assert client.get("/v1/basemaps/tianditu-vector/1/1/1.png").headers["content-type"] == "image/png"
        assert client.get("/v1/basemaps/mapbox-streets/1/1/1.png").headers["content-type"] == "image/png"
        assert client.get("/v1/basemaps/hk-landsd-topographic/14/13386/7148.png").headers["content-type"] == "image/png"
        assert any("mapapi.geodata.gov.hk" in url and "/WGS84/14/13386/7148.png" in url
                   for url in seen_urls)
        assert client.get("/v1/basemaps/not-a-provider/1/1/1.png").status_code == 404
        assert client.get("/v1/basemaps/mapbox-streets/20/1/1.png").status_code == 422
    finally:
        basemap_module.tile.cache_clear()


def test_empty_upstream_tile_becomes_transparent_png(monkeypatch):
    class Headers:
        @staticmethod
        def get_content_type():
            return "application/octet-stream"

    class EmptyResponse:
        status = 204
        headers = Headers()
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        @staticmethod
        def read(_limit): return b""

    monkeypatch.setattr(basemap_module, "urlopen", lambda *_args, **_kwargs: EmptyResponse())
    payload, media_type = basemap_module._download_tile("https://example.invalid/empty.png")
    assert media_type == "image/png"
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")


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
    assert response.status_code == 200
    assert response.json()["default"] == "offline-example"
    provider = next(item for item in response.json()["providers"] if item["id"] == "offline-example")
    assert provider["online"] is False and provider["tile_count"] == 1
    assert "path" not in json.dumps(provider).lower()
    tile = client.get(f"/v1/basemaps/offline-example/{zoom}/{x}/{y}.png")
    assert tile.status_code == 200
    assert tile.headers["content-type"] == "image/png"
    assert "immutable" in tile.headers["cache-control"]

    result = CliRunner().invoke(cli_app, ["basemap", "verify", "--pack",
                                          str(scenario_path / "basemaps" / "example.mbtiles")])
    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["pack"]["tile_count"] == 1
    assert len(report["pack"]["sha256"]) == 64


def test_official_hong_kong_pack_is_preferred_when_multiple_exist(tmp_path, monkeypatch):
    scenario_path = tmp_path / "scenario"
    shutil.copytree(ROOT / "sample_scenario", scenario_path)
    task = json.loads((scenario_path / "task.json").read_text(encoding="utf-8"))
    lon, lat = task["mission"]["start"]
    _write_test_mbtiles(scenario_path / "basemaps" / "example.mbtiles", lon, lat)
    _write_test_mbtiles(scenario_path / "basemaps" / "hong_kong_landsd.mbtiles", lon, lat,
                        "hong-kong-landsd")
    monkeypatch.setenv("ALE_AAM_BASEMAP", "auto")
    bind_scenario(scenario_path)
    assert TestClient(app).get("/v1/basemaps").json()["default"] == "offline-hong-kong-landsd"


def test_web_assets_are_offline():
    for name in ("index.html","app.js","style.css"):
        text = (ROOT / "ale_aam_maptool/web" / name).read_text(encoding="utf-8")
        text = text.replace("http://www.w3.org/2000/svg", "svg-namespace")
        assert "https://" not in text and "http://" not in text
    web = ROOT / "ale_aam_maptool/web"
    index = (web / "index.html").read_text(encoding="utf-8")
    script = (web / "app.js").read_text(encoding="utf-8")
    style = (web / "style.css").read_text(encoding="utf-8")
    assert (web / "vendor/leaflet/leaflet.js").is_file()
    assert (web / "vendor/leaflet/leaflet.css").is_file()
    assert 'src="vendor/leaflet/leaflet.js"' in index
    assert '<svg id="map"' not in index and '<div id="map"' in index
    assert 'class="map-legend"' in index
    assert 'id="route-profile"' in index and 'id="auto-plan"' in index and 'id="plan-all"' in index
    assert index.index('id="mode-inspect"') < index.index('id="route-title"')
    assert "state.view" not in script and "L.geoJSON" in script
    assert "request('/v1/plan'" in script and "request('/v1/plan-all'" in script
    assert ".waypoint-dot" in style and "width: 24px" in style


def test_missing_scenario_is_structured_configuration_error(tmp_path):
    result = CliRunner().invoke(cli_app, ["inspect", "--scenario", str(tmp_path / "missing"), "--json"])
    assert result.exit_code == 2
    error = json.loads(result.stderr.strip().splitlines()[-1])
    assert error["error"]["code"] == "configuration_error"
