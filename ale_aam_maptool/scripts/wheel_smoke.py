import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

scenario = Path(sys.argv[1])
process = subprocess.Popen([
    sys.executable, "-m", "ale_aam_maptool", "serve", "--scenario", str(scenario), "--port", "8765"
])
try:
    for _ in range(40):
        try:
            health = json.load(urlopen("http://127.0.0.1:8765/v1/health"))
            assert health["status"] == "ok"
            break
        except Exception:
            time.sleep(.25)
    else:
        raise RuntimeError("health check timed out")
    layer = json.load(urlopen("http://127.0.0.1:8765/v1/layers/airspace"))
    assert layer["type"] == "FeatureCollection"
    leaflet = urlopen("http://127.0.0.1:8765/vendor/leaflet/leaflet.js").read()
    script = urlopen("http://127.0.0.1:8765/app.js").read()
    assert len(leaflet) > 100_000 and b"Leaflet" in leaflet[:1000]
    assert b"/v1/plan" not in script
    for endpoint in ("/v1/plan", "/v1/plan-all", "/v1/preview"):
        try:
            urlopen("http://127.0.0.1:8765" + endpoint)
            raise AssertionError(f"disabled endpoint is still available: {endpoint}")
        except HTTPError as exc:
            assert exc.code == 404
finally:
    process.terminate()
    process.wait(timeout=10)
