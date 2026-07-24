# ALE v0.2 low-altitude logistics tasks

This directory contains three independent, discoverable `base` tasks. Each task
folder has the current ALE `task_card.json + main.py` package, while `input/` and
`reference/` are the corresponding staged-data payloads. The v0.1 directory is
not modified.

For the complete Chinese installation, task-execution, six-artifact, HTTP/Web,
release-staging, and ALE integration guide, see
[`../silas_maptool/USAGE.zh.md`](../silas_maptool/USAGE.zh.md).

The missions are benchmark simulations only. Their 150 m AGL envelope represents
a hypothetical advanced-operations permission and is not a statement of general
Hong Kong aviation law or authorization for real flight.

Run `python scripts/build_tasks.py`, then `python scripts/refresh_official_sources.py`
to regenerate the reviewed task bundle. The refresh step pins raw LandsD/HKO
snapshots and hashes. It deliberately marks the eSUA layer as a publication
blocker until a fixed licensed CAD export replaces its fixture. Run
`pytest tests` for evaluator mutation tests.

After the Ubuntu/Python 3.12 wheelhouse has been built, run
`python scripts/stage_release.py`. It produces the ALE-native split layout under
`dist/ale-v0.2`: task code in `tasks/transport_safety/` and staged
`input/software/reference` payloads in
`task_data/transport_safety/<task>/base/`. The reference subtree is for ALE's
post-run hidden-reference staging and must never be mounted during agent work.
