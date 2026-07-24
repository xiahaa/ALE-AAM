import json, subprocess, sys, time
from pathlib import Path
from urllib.request import urlopen

scenario, output = map(Path, sys.argv[1:])
for route in "abc":
    data = json.loads((output / f"route_{route}.geojson").read_text())
    assert data["geometry"]["type"] == "LineString"
    assert all("altitude_m_msl" in point for point in data["properties"]["waypoints"])
process = subprocess.Popen([sys.executable, "-m", "silas_maptool", "serve", "--scenario", str(scenario), "--port", "8765"])
try:
    for _ in range(40):
        try:
            assert json.load(urlopen("http://127.0.0.1:8765/v1/health"))["status"] == "ok"; break
        except Exception: time.sleep(.25)
    else: raise RuntimeError("health check timed out")
finally: process.terminate(); process.wait(timeout=10)
