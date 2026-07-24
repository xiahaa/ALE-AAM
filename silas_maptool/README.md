# silas-maptool 0.2.0

Deterministic, offline low-altitude route planning for the ALE benchmark.
Platform-specific release wheels support CPython 3.10–3.13 on Windows x64,
Ubuntu x64, macOS Intel, and macOS Apple Silicon. Release users install a
matching prebuilt wheel and need no C++
compiler, MSVC, Homebrew, apt, or sudo.

This software is for benchmark simulation and demonstrations. It is not a real
flight authorization, dispatch system, or real-time aviation safety product.

Detailed Chinese installation, CLI/API, output-contract, and ALE operations
guide: [USAGE.zh.md](USAGE.zh.md).

## Install

- Windows: place the matching wheel and dependencies in `wheelhouse/`, then run
  `powershell -ExecutionPolicy Bypass -File install.ps1`.
- Ubuntu/macOS: place the wheelhouse beside the script, then run `sh install.sh`.

The wheel workflow uploads one combined artifact named
`silas-maptool-0.2.0-macos-wheels`. It contains CPython 3.10-3.13 wheels for
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
run.sh serve --scenario SCENARIO --host 127.0.0.1 --port 8000
```

Use `run.cmd` in Windows. Successful machine commands emit one JSON object on
stdout. Diagnostics use stderr. Exit codes are 2 configuration/validation, 3 no
feasible route, and 4 native backend failure.

The bound-scenario HTTP API is `/v1/health`, `/v1/scenario`, `/v1/preview`,
`/v1/plan`, `/v1/plan-all`, and `/v1/validate`. The browser cannot request an
arbitrary server path. The web interface and background grid are fully local;
there are no map-tile, CDN, font, or tracking requests.

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
