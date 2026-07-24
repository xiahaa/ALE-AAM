# silas-ale-agent

Standalone repository for the SILAS low-altitude logistics agent benchmark.
It contains the public cross-platform planning tool and the ALE v0.2 task
packages, without the surrounding jps3d repository.

This repository is for benchmark simulation, evaluation, and demonstrations.
It is not a real-flight authorization, dispatch, or aviation-safety system.

## Repository layout

```text
silas-ale-agent/
├── silas_maptool/                 Cross-platform public planning tool
│   ├── silas_maptool/             Python package and offline Web UI
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
    └── silas-maptool-wheels.yml   Windows/Linux/macOS wheel matrix
```

`ALE_v0.1` is historical material and is intentionally not copied into this
standalone repository.

## Build artifacts

The `silas-maptool cross-platform wheels` GitHub Actions workflow builds and
tests CPython 3.10-3.13 wheels for:

- Windows x64
- manylinux x64
- macOS Intel x86_64
- macOS Apple Silicon arm64

The combined Mac artifact is named
`silas-maptool-0.2.0-macos-wheels`. Release wheels and wheelhouses are GitHub
Actions artifacts and are not committed to Git.

## Local use

Windows:

```powershell
cd silas_maptool
powershell -ExecutionPolicy Bypass -File .\install.ps1
.\run.cmd doctor --json
.\run.cmd plan-all --scenario .\sample_scenario --outdir .\output
```

Ubuntu/macOS:

```bash
cd silas_maptool
sh install.sh
sh run.sh doctor --json
sh run.sh plan-all --scenario ./sample_scenario --outdir ./output
```

See [`silas_maptool/USAGE.zh.md`](silas_maptool/USAGE.zh.md) for platform wheel
selection, CLI/API usage, six ALE artifacts, task release staging, and
troubleshooting.

## Tests

Tool tests:

```bash
cd silas_maptool
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

- Tool license: [`silas_maptool/LICENSE`](silas_maptool/LICENSE)
- jps3d license: [`silas_maptool/vendor/jps3d/LICENSE`](silas_maptool/vendor/jps3d/LICENSE)
- Third-party notices: [`silas_maptool/THIRD_PARTY_NOTICES.md`](silas_maptool/THIRD_PARTY_NOTICES.md)
- Scenario sources and hashes: each task's `input/source_manifest.json`

The eSUA/RFZ fixed official snapshot remains a publication blocker until its
fixture is replaced with a licensed, date-pinned CAD export and the manifest
hashes are refreshed.
