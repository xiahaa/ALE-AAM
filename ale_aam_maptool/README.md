# ale-aam-maptool 0.2.0

Deterministic, offline low-altitude route planning for the ALE benchmark.
Platform-specific release wheels support CPython 3.10–3.13 on Windows x64,
Ubuntu x64, macOS Intel, and macOS Apple Silicon. Release users install a
matching prebuilt wheel and need no C++
compiler, MSVC, Homebrew, apt, or sudo.

This software is for benchmark simulation and demonstrations. It is not a real
flight authorization, dispatch system, or real-time aviation safety product.

Detailed Chinese installation, interactive editor, CLI/API, output-contract, and ALE operations
guide: [USAGE.zh.md](USAGE.zh.md).

## Install

- Windows: place the matching wheel and dependencies in `wheelhouse/`, then run
  `powershell -ExecutionPolicy Bypass -File install.ps1`.
- Ubuntu/macOS: place the wheelhouse beside the script, then run `sh install.sh`.

The wheel workflow uploads one combined artifact named
`ale-aam-maptool-0.2.0-macos-wheels`. It contains CPython 3.10-3.13 wheels for
both Intel (`x86_64`) and Apple Silicon (`arm64`). Download the artifact, put
the matching wheel under `dist/macos-arm64/` or `dist/macos-x86_64/`, and run
`sh install.sh`. A maintainer who needs to bootstrap the first artifacts on a
Mac can run `sh scripts/build_macos_wheels.sh`; end users do not run that source
build and do not need Xcode.

Both scripts create `.venv` inside this directory and install with platform
wheels. ALE uses the generated Ubuntu/Python 3.12 wheelhouse with `--no-index`
and `--only-binary=:all:`.

## Stable CLI

```text
run.sh doctor --json
run.sh inspect --scenario SCENARIO --json
run.sh plan --scenario SCENARIO --route A|B|C --out route.geojson
run.sh plan-all --scenario SCENARIO --outdir output
run.sh grid --scenario SCENARIO --route A|B|C --out grid.png
run.sh validate --scenario SCENARIO --output output
run.sh basemap inspect --scenario SCENARIO
run.sh basemap verify --pack SCENARIO/basemaps/example.mbtiles
run.sh serve --scenario SCENARIO --host 127.0.0.1 --port 8000
```

Use `run.cmd` in Windows. Successful machine commands emit one JSON object on
stdout. Diagnostics use stderr. Exit codes are 2 configuration/validation, 3 no
feasible route, and 4 native backend failure.

The bound-scenario HTTP API is `/v1/health`, `/v1/scenario`, `/v1/preview`,
`/v1/layers`, `/v1/environment`, `/v1/basemaps`, `/v1/plan`, `/v1/plan-all`,
and `/v1/validate`.
The Web interface loads the bound DEM/building/airspace/weather/population layers,
supports local GeoJSON/ZIP overlays, inspects environment values, draws and edits
waypoints, and exports a GeoJSON `LineString`. The browser cannot request an
arbitrary server path. Offline scenario layers remain the default and require no
network. For local development or demonstrations, TianDiTu and Mapbox can be
enabled through the server-side basemap proxy.

Copy `.env.example` to `.env`, populate the provider values locally, and never
commit that file. The browser receives only `/v1/basemaps/...` image URLs: provider
credentials are not embedded in HTML/JavaScript, API metadata, logs, or Git. Static
Web assets use no CDN or tracking service. Online basemaps are deliberately not
enabled in the formal offline ALE task runtime.

### Minimal offline basemap example

The three ALE v0.2 scenarios include a small `basemaps/example.mbtiles` pack at
zoom levels 12-14. It is rendered deterministically from the bundled DEM and
building footprints and makes zero network requests. When no explicit provider
is selected, `ALE_AAM_BASEMAP=auto` selects this pack automatically.

Use `basemap inspect` to list a scenario's packs and `basemap verify` to validate
the SQLite schema, zoom range, tile count, bounds, and SHA-256. Maintainers can
regenerate an example without provider credentials:

```text
python scripts/create_example_basemap.py --scenario ../ALE_v0.2/urban_drone_logistics/input/gis
```

Large production `.mbtiles` archives remain ignored by Git and should be
distributed as versioned release assets. The committed examples contain no
TianDiTu, Mapbox, or OpenStreetMap-hosted tiles.

## Scenario contract

`task.json` schema 2.0 declares the mission, layers, aircraft, hard constraints,
and A/B/C route profiles. Every machine coordinate is `[longitude, latitude]`.
Waypoints contain both `altitude_m_agl` and `altitude_m_msl`.

The public tool contains no reference generator, hidden score, expert answer, or
private grading formula. `validate` checks schemas and explicit constraints only.

## Build and test

The extension uses `pyproject.toml`, scikit-build-core, CMake, pybind11, vendored
Eigen headers, and the BSD-3-Clause jps3d source. `cibuildwheel` builds and tests
the release matrix. For a developer source build:

```text
python -m pip install .[test]
python -m pytest tests
```

See `LICENSE`, `THIRD_PARTY_NOTICES.md`, and `vendor/jps3d/LICENSE`.
