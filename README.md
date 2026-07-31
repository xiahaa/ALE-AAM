# ALE-AAM

English | [中文](README.zh-CN.md)

ALE-AAM is a cross-platform, offline-first GIS toolkit for the Hong Kong
low-altitude logistics tasks contributed to [Agents' Last Exam
(ALE)](https://agents-last-exam.org/). It helps users and agents load a task
scenario, inspect the operating environment, draw and edit candidate routes,
export GeoJSON, and validate the required deliverables.

The repository contains the map tool and three independently packaged ALE task
variants:

| Task | Scenario |
|---|---|
| `urban_drone_logistics` | Dense urban logistics in Kowloon |
| `cross_sea_drone_logistics` | Cross-sea logistics in southern Hong Kong |
| `emergency_blood_transport` | Time-critical blood transport on Hong Kong Island |

> This project is intended for benchmark evaluation and simulation. It is not
> a flight authorization, dispatch service, or operational aviation-safety
> system.

## Features

- Load deterministic task GIS from a local scenario directory.
- Display terrain, 3D buildings, restricted airspace, population density,
  weather, and emergency-site layers.
- Query structured environment values at any point within the task extent.
- Work offline with the bundled Hong Kong Lands Department basemap.
- Draw, drag, and edit independent route candidates A, B, and C.
- Set waypoint AGL altitude and speed, with MSL altitude sampled from the DEM.
- Export standards-compliant GeoJSON using `[longitude, latitude]` coordinates.
- Validate the public route and six-file submission contract.
- Run on Windows x64, Ubuntu x64, macOS Intel, and Apple Silicon.

## Downloadable packages

Open the repository's **Actions** page and select a successful **ALE-AAM
package** workflow run. The workflow publishes these artifacts:

| Artifact | Use |
|---|---|
| `ale-aam-maptool-1.0.0-universal-wheel` | Map tool for CPython 3.10–3.13 on all supported platforms |
| `ale-aam-ubuntu-py312-wheelhouse` | Complete offline installation set for the ALE Ubuntu/Python 3.12 environment |
| `ale-aam-urban-drone-logistics-base` | ALE upload package for the urban logistics task |
| `ale-aam-cross-sea-drone-logistics-base` | ALE upload package for the cross-sea task |
| `ale-aam-emergency-blood-transport-base` | ALE upload package for the blood-transport task |

Each task artifact contains one task variant and can be uploaded independently.
Do not combine the three task ZIP files before submission.

## Install the map tool

The map tool supports CPython 3.10, 3.11, 3.12, and 3.13. The supplied scripts
create a project-local `.venv` and do not require administrator privileges.

### Online dependency installation

Download and extract `ale-aam-maptool-1.0.0-universal-wheel`, then place the
wheel in `ale_aam_maptool/dist/`.

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
./run.sh doctor --json
```

### Fully offline installation

Place the map-tool wheel and all dependency wheels in
`ale_aam_maptool/wheelhouse/`, then run the same installation script. The ALE
Ubuntu package already provides the complete Python 3.12 wheelhouse.

A successful health check prints JSON containing `"ok": true`.

## Quick start

The repository includes a small deterministic example scenario.

Windows:

```powershell
cd ale_aam_maptool
.\run.cmd inspect --scenario .\sample_scenario --json
.\run.cmd serve --scenario .\sample_scenario --host 127.0.0.1 --port 8000
```

Ubuntu or macOS:

```bash
cd ale_aam_maptool
./run.sh inspect --scenario ./sample_scenario --json
./run.sh serve --scenario ./sample_scenario --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` in a browser. Replace `sample_scenario` with the
`input/gis` directory supplied with a task when working on an ALE case.

The server is bound to the scenario selected at startup. Browser requests
cannot select arbitrary directories on the host machine.

## Web workflow

1. Select the bundled offline basemap.
2. Toggle the environment layers needed for the current analysis.
3. Use **View** mode and click the map to inspect terrain, weather, population,
   building, airspace, and emergency-site information.
4. Select candidate A, B, or C. Each candidate maintains an independent draft
   in the current browser session.
5. Select **Draw waypoints**, click the map to add intermediate waypoints, and
   drag markers to refine the route.
6. Edit AGL altitude and speed for each waypoint.
7. Export the candidate as `route_a.geojson`, `route_b.geojson`, or
   `route_c.geojson`.
8. Complete the remaining risk assessment, selected route, and emergency plan
   required by the task instructions.

The yellow dashed rectangle is the task's valid analysis extent. The basemap
may show additional cartographic context outside this rectangle, but structured
task queries and route waypoints must remain inside it.

## Command-line interface

```text
doctor --json
inspect --scenario DIR --json
validate --scenario DIR --output DIR
basemap inspect --scenario DIR
basemap verify --pack FILE.mbtiles
serve --scenario DIR --host 127.0.0.1 --port 8000
```

Examples:

```bash
ale-aam-maptool doctor --json
ale-aam-maptool inspect --scenario input/gis --json
ale-aam-maptool validate --scenario input/gis --output output
ale-aam-maptool basemap inspect --scenario input/gis
ale-aam-maptool serve --scenario input/gis --host 127.0.0.1 --port 8000
```

Successful machine-readable commands write JSON to stdout. Diagnostic messages
and errors are written to stderr.

## Local HTTP API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/v1/health` | Service health and package version |
| GET | `/v1/scenario` | Bound scenario, task extent, aircraft, and constraints |
| GET | `/v1/layers` | Available layer catalogue |
| GET | `/v1/layers/{id}` | Vector layer as GeoJSON |
| GET | `/v1/layers/{id}/preview` | Deterministic raster preview |
| GET | `/v1/environment?lon=&lat=` | Structured point query |
| GET | `/v1/basemaps` | Available basemap catalogue |
| GET | `/v1/basemaps/{id}/{z}/{x}/{y}.png` | Validated basemap tile |
| POST | `/v1/validate` | Validate one submitted GeoJSON feature |

## Scenario contents

Each task input includes:

- `task_prompt.md` and `routing_guidelines.md`;
- `tool_usage.md` and `output_contract.json`;
- a risk-assessment rubric and emergency-planning manual;
- `source_manifest.json` with source, CRS, acquisition date, transformation,
  and SHA-256 information;
- `gis/task.json` with the mission, aircraft, constraints, layers, and route
  profiles;
- 5 m terrain, building heights, restricted airspace, population, weather,
  emergency sites, and an offline basemap.

GeoJSON and all machine interfaces use `[longitude, latitude]`. Waypoint
altitudes include both `altitude_m_agl` and `altitude_m_msl`.

## Required task outputs

An ALE submission must contain exactly these six files:

```text
route_a.geojson
route_b.geojson
route_c.geojson
route_final.geojson
risk_assessment.csv
emergency_response_plan.md
```

Each candidate route must:

- be a GeoJSON `Feature` with `LineString` geometry;
- contain at least five coordinates;
- start and end at the task-defined endpoints;
- remain within the declared task extent;
- include matching waypoint records with AGL altitude, MSL altitude, and speed;
- satisfy the task's altitude, airspace, building-clearance, speed, and energy
  constraints; and
- represent the objective assigned to candidate A, B, or C.

The risk CSV contains six dimensions plus one total row for each candidate, for
21 data rows in total. The emergency plan must follow the scenario-specific
manual and cover all three failure levels.

Run the public validation before submission:

```bash
ale-aam-maptool validate --scenario input/gis --output output
```

## Basemaps and credentials

The bundled Hong Kong MBTiles basemap works without network access or API keys.
Optional online providers can be configured locally by copying `.env.example`
to `.env`:

```text
ALE_AAM_BASEMAP=auto
ALE_AAM_TIANDITU_TOKEN=...
ALE_AAM_MAPBOX_TOKEN=...
ALE_AAM_MAPBOX_STYLE=mapbox/streets-v12
```

Keep `.env` local. Credentials must not be committed, embedded in JavaScript,
included in task packages, or exposed in API responses. ALE execution should
use the bundled offline basemap.

## Verification

From the repository root:

```bash
python -m pip install "./ale_aam_maptool[test]"
python -m pytest ale_aam_maptool/tests
node --check ale_aam_maptool/ale_aam_maptool/web/app.js
```

GitHub Actions additionally installs the wheel on Windows, Ubuntu, Intel macOS,
and Apple Silicon macOS with every supported Python version.

## Contributors and contact

- **Zhang Lei** — [zhanglei1@idea.edu.cn](mailto:zhanglei1@idea.edu.cn)
- **Meng Luoheng** — [mengluoheng@idea.edu.cn](mailto:mengluoheng@idea.edu.cn)
- **Xiao Hu** — [huxiao1@idea.edu.cn](mailto:huxiao1@idea.edu.cn)

Lower Airspace Economy Research Institute, International Digital Economy
Academy (IDEA), Shenzhen 510085, China.

## Data and licensing

Source provenance and checksums are recorded in each task's
`source_manifest.json`. The offline basemap attribution is “Map from Lands
Department, HKSAR Government” and its reuse is governed by the DATA.GOV.HK
Terms and Conditions. Project and third-party notices are provided in
`LICENSE` and `ale_aam_maptool/THIRD_PARTY_NOTICES.md`.

Confirm the applicable source-data redistribution terms before distributing a
task package outside the authorized submission workflow.

## Troubleshooting

- **Blank map:** choose the bundled offline Lands Department basemap. Optional
  online providers may be unavailable on some networks.
- **A point cannot be queried or used as a waypoint:** move it inside the yellow
  task-extent rectangle.
- **GeoJSON export reports a missing MSL altitude:** the waypoint has no valid
  terrain sample; move it within the task extent and retry.
- **Validation reports missing files:** `validate` checks the complete six-file
  output directory.
- **Wheel installation fails offline:** confirm that `wheelhouse/` contains the
  map-tool wheel and every platform-compatible dependency wheel.
