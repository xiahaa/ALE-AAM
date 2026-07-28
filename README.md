# ALE-AAM 1.0.0

English documentation | [中文说明](README.zh-CN.md)

ALE-AAM is the final offline GIS inspection and manual route-editing tool for
three Hong Kong low-altitude logistics tasks in Agents' Last Exam (ALE). It
loads the delivered scenario, presents structured environment layers, lets a
user manually draw and edit candidate routes A/B/C, exports GeoJSON, and checks
the public output contract.

Automatic route planning is intentionally disabled in the final release. There
is no `plan` or `plan-all` CLI command, no `/v1/plan` HTTP endpoint, no public
Python planning API, and no native JPS extension in the wheel. This preserves
the benchmark's reasoning difficulty: the agent must interpret the supplied
GIS and constraints and construct its own candidates.

This repository is for benchmark simulation and evaluation only. It is not a
real-flight authorization, dispatch system, or aviation-safety system.

## 1. Final repository contents

```text
ALE-AAM/
├── README.md / README.zh-CN.md       Final English and Chinese manuals
├── ale_aam_maptool/                  Cross-platform public tool
│   ├── ale_aam_maptool/              Python package and offline Web UI
│   ├── sample_scenario/              Deterministic smoke-test scenario
│   ├── scripts/                      Release smoke tests only
│   ├── tests/                        Final capability/API tests
│   ├── install.ps1 / install.sh
│   ├── run.cmd / run.sh
│   └── pyproject.toml
├── ALE_v0.2/                         Authoritative final ALE task sources
│   ├── urban_drone_logistics/
│   ├── cross_sea_drone_logistics/
│   ├── emergency_blood_transport/
│   ├── _private/evaluator.py
│   ├── scripts/stage_release.py
│   └── tests/
├── data/                             Reviewed source airspace snapshot
└── .github/workflows/                Build and cross-platform smoke CI
```

Development-only generators, obsolete planning code, CMake/JPS sources, old
manuals, and review notes live locally under ignored `legacy/`. They are not
part of Git, wheels, or ALE upload archives.

## 2. Task identity and upload model

`ALE_v0.2` is the source of truth for the final tasks. It is not a tool-only
development directory. The repository groups the three tasks for maintenance,
but they are three independent ALE task IDs, each with one public `base`
variant:

| Task ID | Base scenario |
|---|---|
| `transport_safety/urban_drone_logistics` | Dense Kowloon urban logistics |
| `transport_safety/cross_sea_drone_logistics` | Southern Hong Kong cross-sea logistics |
| `transport_safety/emergency_blood_transport` | Hong Kong Island emergency blood transport |

Each source directory contains the formal `task_card.json`, `main.py`, `input/`,
and hidden `reference/`. The release script converts that shared source tree
into three separate, self-contained upload directories and ZIP files. This
matches ALE's current [task package](https://agents-last-exam.org/docs/ale/pages/add-task.html)
and [data staging](https://agents-last-exam.org/docs/ale/pages/tasks.html) model.

Do not combine the final tool with `ALE_v0.1/input`. v0.1 is historical and has
older data, contracts, and packaging assumptions.

## 3. Supported systems and wheel

The final wheel is pure Python and universal:

```text
ale_aam_maptool-1.0.0-py3-none-any.whl
```

It supports CPython 3.10–3.13 on Windows x64, Ubuntu x64, macOS Intel, and macOS
Apple Silicon. Users do not need CMake, a C++ compiler, Homebrew, apt, or MSVC.
Platform-specific wheels are still needed for third-party dependencies such as
Rasterio and NumPy when building a completely offline wheelhouse.

GitHub Actions publishes:

- `ale-aam-maptool-1.0.0-universal-wheel` — installable on all supported systems.
- `ale-aam-ubuntu-py312-wheelhouse` — the tool plus Linux/Python 3.12 dependency
  wheels for offline ALE staging.
- `ale-aam-urban-drone-logistics-base` — upload ZIP for the urban task only.
- `ale-aam-cross-sea-drone-logistics-base` — upload ZIP for the cross-sea task only.
- `ale-aam-emergency-blood-transport-base` — upload ZIP for the blood task only.

Download artifacts from the repository's **Actions** page after the `ALE-AAM
final package` workflow succeeds.

## 4. Installation

Place the universal tool wheel under `ale_aam_maptool/dist/`. For a fully
offline installation, place the tool and every dependency wheel under
`ale_aam_maptool/wheelhouse/`.

Windows PowerShell:

```powershell
cd ale_aam_maptool
powershell -ExecutionPolicy Bypass -File .\install.ps1
.\run.cmd doctor --json
```

Ubuntu or macOS:

```bash
cd ale_aam_maptool
sh install.sh
sh run.sh doctor --json
```

The scripts create a project-local `.venv/`. `doctor` must report:

```json
{
  "ok": true,
  "version": "1.0.0",
  "capabilities": {
    "inspect_environment": true,
    "manual_route_editing": true,
    "geojson_export": true,
    "automatic_planning": false
  }
}
```

## 5. Start the offline Web UI

Windows:

```powershell
.\run.cmd serve --scenario ..\ALE_v0.2\urban_drone_logistics\input\gis --host 127.0.0.1 --port 8000
```

Ubuntu/macOS:

```bash
./run.sh serve --scenario ../ALE_v0.2/urban_drone_logistics/input/gis --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. The server is bound to the scenario supplied at
startup; the browser cannot request arbitrary server filesystem paths.

### Manual workflow

1. Select the scenario-local Hong Kong Lands Department offline basemap.
2. Toggle buildings, airspace, weather, population, terrain, and emergency sites.
3. Use **View** mode to inspect a point's structured environment values.
4. In the route section choose A, B, or C. Each candidate has an independent
   in-page draft.
5. Select **Draw waypoints**, click to add intermediate points, drag points to
   adjust them, and edit AGL altitude and speed.
6. Export the current candidate. The filenames are `route_a.geojson`,
   `route_b.geojson`, or `route_c.geojson`.
7. Choose the other candidate IDs and repeat. Create `route_final.geojson`, the
   risk CSV, and the emergency plan as required by the task contract.

The yellow dashed rectangle is `task.json.planning_extent`. Structured queries
and route waypoints are allowed only inside it. The offline cartographic tiles
extend by 20% for visual context; pixels outside the rectangle are never
planning or scoring data. All machine coordinates are `[longitude, latitude]`.

## 6. Optional online basemaps and secret handling

The delivered Hong Kong MBTiles require no credential and work without network
access. Optional Tianditu and Mapbox layers are server-side proxies.

Copy `.env.example` to `.env` and set values locally:

```text
ALE_AAM_BASEMAP=auto
ALE_AAM_TIANDITU_TOKEN=...
ALE_AAM_MAPBOX_TOKEN=...
ALE_AAM_MAPBOX_STYLE=mapbox/streets-v12
```

Never commit `.env`, paste credentials into JavaScript, include them in an ALE
archive, or expose them through `/v1/basemaps`. `.env` and secret variants are
ignored by Git. Formal ALE runs must use the delivered offline basemap and must
not depend on these services.

## 7. Final CLI and HTTP contracts

CLI commands:

```text
doctor --json
inspect --scenario DIR --json
validate --scenario DIR --output DIR
basemap inspect --scenario DIR
basemap verify --pack FILE.mbtiles
serve --scenario DIR --host 127.0.0.1 --port 8000
```

There is deliberately no `plan`, `plan-all`, or planning-grid command.

Versioned HTTP endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/v1/health` | Version and server health |
| GET | `/v1/scenario` | Bound scenario metadata and bounds |
| GET | `/v1/layers` | Layer catalogue |
| GET | `/v1/layers/{id}` | Vector GeoJSON |
| GET | `/v1/layers/{id}/preview` | Deterministic raster preview |
| GET | `/v1/environment?lon=&lat=` | Structured point query |
| GET | `/v1/basemaps` | Credential-free provider catalogue |
| GET | `/v1/basemaps/{id}/{z}/{x}/{y}.png` | Validated tile proxy |
| POST | `/v1/validate` | Validate one submitted GeoJSON feature |

`/v1/plan`, `/v1/plan-all`, and `/v1/preview` are absent.

## 8. Scenario data and output contract

Each final input contains:

- `task_prompt.md`, `routing_guidelines.md`, `tool_usage.md`;
- `output_contract.json`, risk rubric, and emergency-planning manual;
- `source_manifest.json` with provenance and SHA-256 values;
- `gis/task.json`, 5 m DTM, 3D buildings, RFZ polygons, population density,
  weather grid, emergency sites, and a bounded LandsD MBTiles pack.

Agents must produce exactly six artifacts:

```text
route_a.geojson
route_b.geojson
route_c.geojson
route_final.geojson
risk_assessment.csv
emergency_response_plan.md
```

Routes must contain at least five `[longitude, latitude]` points, start and end
at the task endpoints, remain within `planning_extent`, and provide per-waypoint
`altitude_m_agl`, `altitude_m_msl`, and `speed_ms`. `validate` checks public
schema and explicit constraints only. It does not plan, score, select, or repair
a route.

## 9. Build and verify the final wheel

```bash
python -m pip install build
python -m build --wheel --outdir dist ale_aam_maptool
python -m pip install "ale_aam_maptool[test]"
python -m pytest ale_aam_maptool/tests ALE_v0.2/tests
node --check ale_aam_maptool/ale_aam_maptool/web/app.js
```

The resulting filename must end in `py3-none-any.whl`. A wheel containing a
`.so`, `.pyd`, `.dylib`, JPS module, or planning endpoint is not a final release.

## 10. Build three independent ALE upload packages

First download/extract `ale-aam-ubuntu-py312-wheelhouse` into a local
`wheelhouse/`, then run:

```bash
python ALE_v0.2/scripts/stage_release.py \
  --wheelhouse wheelhouse \
  --out ALE_v0.2/dist/ale-aam-final
```

The command produces:

```text
ale-aam-urban_drone_logistics-base.zip
ale-aam-cross_sea_drone_logistics-base.zip
ale-aam-emergency_blood_transport-base.zip
```

Each ZIP contains exactly one task:

```text
tasks/transport_safety/_private/evaluator.py
tasks/transport_safety/<task>/main.py
tasks/transport_safety/<task>/task_card.json
task_data/transport_safety/<task>/base/input/
task_data/transport_safety/<task>/base/software/wheelhouse/
task_data/transport_safety/<task>/base/reference/
release_manifest.json
```

The platform stages `input/` and `software/` before the agent run. It must stage
`reference/` only after the agent has finished. Never move `reference` under
`input` and never include evaluator formulas in agent-visible materials.

Use `--task <name>` to stage one task only. The output target must not already
exist; this prevents silently mixing an old package with a new release.

## 11. Data, licensing, and release blocker

The task data records source URL, acquisition date, CRS, conversion procedure,
and SHA-256 in each `input/source_manifest.json`. The offline map attribution is
“Map from Lands Department, HKSAR Government” and reuse is subject to the
DATA.GOV.HK Terms and Conditions. Leaflet's BSD-2-Clause notice is bundled with
the Web assets; project notices are in `LICENSE` and `THIRD_PARTY_NOTICES.md`.

The 2026-07-24 eSUA/RFZ archive is hash-pinned and clipped into each task. Its
redistribution terms remain a publication blocker: confirm them before any
external task upload, even when the GitHub repository is private.

## 12. Troubleshooting

- **Blank basemap:** select the delivered offline LandsD layer. Online providers
  are optional and may be blocked in mainland networks.
- **A coordinate cannot be queried or dragged:** it is outside the yellow
  `planning_extent`; only cartographic context exists there.
- **Export lacks MSL altitude:** the waypoint has no valid DEM sample. Move it
  inside the task extent and retry.
- **`validate` reports missing files:** it validates the full six-file output
  directory, not only the currently exported route.
- **No `plan` command:** expected final behavior. Automatic planning is disabled,
  not an installation failure.
- **Wheel not found:** download the `1.0.0` universal wheel; do not use old
  CPython/platform-specific `0.3.x` JPS wheels.
