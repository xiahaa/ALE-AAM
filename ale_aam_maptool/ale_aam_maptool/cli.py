from __future__ import annotations

import json
import logging
import platform
import sys
from pathlib import Path

import typer

from . import __version__
from .errors import MaptoolError

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Offline GIS inspection and manual route-editing toolkit.",
)
basemap_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Inspect and verify scenario-local offline basemap packs.",
)
app.add_typer(basemap_app, name="basemap")
log = logging.getLogger("ale_aam_maptool")


def _emit(value):
    typer.echo(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


def _fail(exc):
    if isinstance(exc, MaptoolError):
        code, name = exc.exit_code, exc.error_code
    elif isinstance(exc, (ValueError, FileNotFoundError, json.JSONDecodeError)):
        code, name = 2, "configuration_error"
    else:
        code, name = 4, "internal_error"
    typer.echo(
        json.dumps({"ok": False, "error": {"code": name, "message": str(exc)}}, ensure_ascii=False),
        err=True,
    )
    raise typer.Exit(code=code)


def _load(path, resolution):
    from .scenario import Scenario

    try:
        return Scenario.load(path, resolution=resolution)
    except Exception as exc:
        _fail(exc)


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON.")):
    """Check interpreter, package assets, and the final capability policy."""
    web = Path(__file__).parent / "web" / "index.html"
    info = {
        "ok": True,
        "version": __version__,
        "python": platform.python_version(),
        "python_supported": (3, 10) <= sys.version_info[:2] <= (3, 13),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "offline_web": web.exists(),
        "capabilities": {
            "inspect_environment": True,
            "manual_route_editing": True,
            "geojson_export": True,
            "automatic_planning": False,
        },
    }
    info["ok"] = info["python_supported"] and info["offline_web"]
    _emit(info)
    if not info["ok"]:
        raise typer.Exit(code=2)


@app.command()
def inspect(
    scenario: Path = typer.Option(...),
    json_output: bool = typer.Option(False, "--json"),
    resolution: float = 5.0,
):
    sc = _load(scenario, resolution)
    west, south, east, north = sc.lonlat_bounds()
    _emit({
        "ok": True,
        "schema_version": sc.task["schema_version"],
        "mission": sc.task["mission"],
        "route_profiles": sc.task["route_profiles"],
        "grid": {
            "width": sc.grid.width,
            "height": sc.grid.height,
            "resolution_m": sc.grid.resolution,
            "crs": str(sc.grid.crs),
        },
        "extent": {"west": west, "south": south, "east": east, "north": north},
        "planning_extent": sc.task.get("planning_extent"),
        "layers": sc.task["layers"],
    })


@app.command()
def validate(
    scenario: Path = typer.Option(...),
    output: Path = typer.Option(...),
    resolution: float = 5.0,
):
    from .validator import validate_output

    report = validate_output(output, _load(scenario, resolution).task)
    _emit(report)
    if not report["ok"]:
        raise typer.Exit(code=2)


@basemap_app.command(name="inspect")
def basemap_inspect(scenario: Path = typer.Option(...)):
    """List validated MBTiles packs in SCENARIO/basemaps."""
    from .offline_basemap import discover_packs, public_pack

    try:
        sc = _load(scenario, 5.0)
        packs = [public_pack(pack) for pack in discover_packs(sc.path)]
        _emit({"ok": True, "scenario": str(sc.path), "packs": packs})
    except typer.Exit:
        raise
    except Exception as exc:
        _fail(exc)


@basemap_app.command(name="verify")
def basemap_verify(pack: Path = typer.Option(...)):
    """Validate one MBTiles pack and emit its SHA-256 and coverage metadata."""
    from .offline_basemap import inspect_pack

    try:
        _emit({"ok": True, "pack": inspect_pack(pack, include_sha256=True)})
    except Exception as exc:
        _fail(exc)


@app.command()
def serve(
    scenario: Path = typer.Option(...),
    host: str = typer.Option("127.0.0.1"),
    port: int = 8000,
    resolution: float = 5.0,
):
    import uvicorn
    from .server import app as api, bind_scenario

    try:
        bind_scenario(scenario, resolution)
    except Exception as exc:
        _fail(exc)
    uvicorn.run(api, host=host, port=port, log_level="warning")
