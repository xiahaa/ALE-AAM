import os
import subprocess
import sys
import tempfile
from pathlib import Path

root, scenario = Path.cwd(), Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as directory:
    venv = Path(directory) / "venv"
    subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.check_call([
        str(python), "-m", "pip", "install", "--no-index", "--find-links",
        str(root / "wheelhouse"), "ale-aam-maptool",
    ])
    subprocess.check_call([str(python), "-m", "ale_aam_maptool", "doctor", "--json"])
    subprocess.check_call([
        str(python), "-m", "ale_aam_maptool", "inspect", "--scenario", str(scenario), "--json",
    ])
    subprocess.check_call([str(python), root / "ale_aam_maptool/scripts/wheel_smoke.py", scenario])
