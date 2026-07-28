# ALE-AAM

Standalone repository for the ALE-AAM low-altitude logistics agent benchmark.
It contains the public cross-platform planning tool and the ALE v0.2 task
packages, without the surrounding jps3d repository.

Each ALE v0.2 case includes a bounded z12-z17 snapshot from the official Hong
Kong Lands Department topographic map API, so the Web UI has a high-resolution
Hong Kong background without network access or provider credentials.
The tiles are visual context only: planning and evaluation continue to use the
distributed 5 m DTM and structured building, airspace, population, weather, and
emergency-site layers.

This repository is for benchmark simulation, evaluation, and demonstrations.
It is not a real-flight authorization, dispatch, or aviation-safety system.

## Repository layout

```text
ALE-AAM/
├── data/                            User-provided Hong Kong airspace snapshot
├── ale_aam_maptool/                 Cross-platform public planning tool
│   ├── ale_aam_maptool/             Python package and offline Web UI
│   ├── vendor/jps3d/              Vendored BSD-3-Clause JPS backend
│   ├── sample_scenario/           Small deterministic smoke scenario
│   ├── tests/
│   ├── install.ps1 / install.sh
│   ├── run.cmd / run.sh
│   └── USAGE.zh.md                Detailed Chinese guide
├── ALE_v0.2/                      Three ALE task packages and private grader
│   ├── urban_drone_logistics/
│   ├── cross_sea_drone_logistics/
│   ├── emergency_blood_transport/
│   ├── _private/
│   ├── scripts/
│   └── tests/
└── .github/workflows/
    └── ale-aam-maptool-wheels.yml   Windows/Linux/macOS wheel matrix
```

`ALE_v0.1` is historical material and is intentionally not copied into this
standalone repository.

## Build artifacts

The `ale-aam-maptool cross-platform wheels` GitHub Actions workflow builds and
tests CPython 3.10-3.13 wheels for:

- Windows x64
- manylinux x64
- macOS Intel x86_64
- macOS Apple Silicon arm64

The combined Mac artifact is named
`ale-aam-maptool-0.2.1-macos-wheels`. Release wheels and wheelhouses are GitHub
Actions artifacts and are not committed to Git.

## Local use

Windows:

```powershell
cd ale_aam_maptool
powershell -ExecutionPolicy Bypass -File .\install.ps1
.\run.cmd doctor --json
.\run.cmd plan-all --scenario .\sample_scenario --outdir .\output
```

Ubuntu/macOS:

```bash
cd ale_aam_maptool
sh install.sh
sh run.sh doctor --json
sh run.sh plan-all --scenario ./sample_scenario --outdir ./output
```

The offline-first Web interface follows one primary workflow: load scenario/local
data, inspect environment layers, draw or edit waypoints, and export one GeoJSON
`LineString`. Start it with `serve`, open the printed local URL, and optionally
load [`data/hong_kong_airspace_20260724.zip`](data/hong_kong_airspace_20260724.zip)
directly in the browser. The shipped LandsD snapshot and scenario layers work
without OSM, a CDN, or any external request. Buildings, airspace and emergency
sites remain true vector overlays at every zoom level. Local demonstrations may
also use the key-free live LandsD map or enable TianDiTu/Mapbox through the
credential-hiding proxy; formal ALE task execution remains offline.

See [`ale_aam_maptool/USAGE.zh.md`](ale_aam_maptool/USAGE.zh.md) for platform wheel
selection, CLI/API usage, six ALE artifacts, task release staging, and
troubleshooting.

## Tests

Tool tests:

```bash
cd ale_aam_maptool
python -m pip install .[test]
python -m pytest tests
```

ALE source/evaluator tests:

```bash
cd ALE_v0.2
python -m pytest tests
```

## Reference isolation

The public tool contains no reference generator or private scoring formula.
During an ALE run, the agent may see only staged `input/`, `software/`, and its
own `output/`. The task-data provider must stage `reference/` only after the
agent has finished, before `evaluate()` runs.

## Licensing and data provenance

- Tool license: [`ale_aam_maptool/LICENSE`](ale_aam_maptool/LICENSE)
- jps3d license: [`ale_aam_maptool/vendor/jps3d/LICENSE`](ale_aam_maptool/vendor/jps3d/LICENSE)
- Third-party notices: [`ale_aam_maptool/THIRD_PARTY_NOTICES.md`](ale_aam_maptool/THIRD_PARTY_NOTICES.md)
- Scenario sources and hashes: each task's `input/source_manifest.json`

The supplied 2026-07-24 eSUA/RFZ export is now clipped into all three cases and
hash-pinned. Before public benchmark publication, the team must still confirm
the source redistribution terms recorded in each manifest.
