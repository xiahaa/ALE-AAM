import json
import io
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
    start = client.get("/v1/scenario").json()["mission"]["start"]
    environment = client.get("/v1/environment", params={"lon": start[0], "lat": start[1]})
    assert environment.status_code == 200
    assert environment.json()["coordinate"] == pytest.approx(start)
    basemaps = client.get("/v1/basemaps")
    assert basemaps.status_code == 200
    assert any(provider["id"] == "offline" for provider in basemaps.json()["providers"])
    assert "token" not in basemaps.text.lower()
    assert "access_token" not in basemaps.text.lower()
    paths = client.get("/openapi.json").json()["paths"]
    assert "/scenario/load" not in paths
    assert set(("/v1/health","/v1/scenario","/v1/preview","/v1/layers",
                "/v1/layers/{layer_id}/preview", "/v1/environment",
                "/v1/basemaps", "/v1/basemaps/{provider_id}/{z}/{x}/{y}.png",
                "/v1/plan","/v1/plan-all","/v1/validate")) <= set(paths)


def test_basemap_proxy_keeps_credentials_server_side(monkeypatch):
    image = Image.new("RGBA", (4, 4), (34, 92, 120, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    tile_bytes = buffer.getvalue()

    monkeypatch.setenv("ALE_AAM_TIANDITU_TOKEN", "test-tianditu-secret")
    monkeypatch.setenv("ALE_AAM_MAPBOX_TOKEN", "test-mapbox-secret")
    monkeypatch.setattr(basemap_module, "_download_tile", lambda _url: (tile_bytes, "image/png"))
    basemap_module.tile.cache_clear()
    try:
        client = TestClient(app)
        catalog = client.get("/v1/basemaps").json()
        assert {item["id"] for item in catalog["providers"] if item["available"]} >= {
            "offline", "tianditu-vector", "mapbox-streets"
        }
        assert "test-tianditu-secret" not in json.dumps(catalog)
        assert "test-mapbox-secret" not in json.dumps(catalog)
        assert client.get("/v1/basemaps/tianditu-vector/1/1/1.png").headers["content-type"] == "image/png"
        assert client.get("/v1/basemaps/mapbox-streets/1/1/1.png").headers["content-type"] == "image/png"
        assert client.get("/v1/basemaps/not-a-provider/1/1/1.png").status_code == 404
        assert client.get("/v1/basemaps/mapbox-streets/20/1/1.png").status_code == 422
    finally:
        basemap_module.tile.cache_clear()


def test_web_assets_are_offline():
    for name in ("index.html","app.js","style.css"):
        text = (ROOT / "ale_aam_maptool/web" / name).read_text(encoding="utf-8")
        text = text.replace("http://www.w3.org/2000/svg", "svg-namespace")
        assert "https://" not in text and "http://" not in text


def test_missing_scenario_is_structured_configuration_error(tmp_path):
    result = CliRunner().invoke(cli_app, ["inspect", "--scenario", str(tmp_path / "missing"), "--json"])
    assert result.exit_code == 2
    error = json.loads(result.stderr.strip().splitlines()[-1])
    assert error["error"]["code"] == "configuration_error"
