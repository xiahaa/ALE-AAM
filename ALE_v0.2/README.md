# ALE v0.2 low-altitude logistics tasks

This directory contains three independent, discoverable `base` tasks. Each task
folder has the current ALE `task_card.json + main.py` package, while `input/` and
`reference/` are the corresponding staged-data payloads. The v0.1 directory is
not modified.

For the complete Chinese installation, task-execution, six-artifact, HTTP/Web,
release-staging, and ALE integration guide, see
[`../ale_aam_maptool/USAGE.zh.md`](../ale_aam_maptool/USAGE.zh.md).

The missions are benchmark simulations only. Their 150 m AGL envelope represents
a hypothetical advanced-operations permission and is not a statement of general
Hong Kong aviation law or authorization for real flight.

Run `python scripts/build_tasks.py`, `python scripts/refresh_official_sources.py`,
and `python scripts/import_hk_airspace_snapshot.py` in that order to regenerate
the reviewed task GIS. Build the bounded LandsD MBTiles with
`../ale_aam_maptool/scripts/build_hk_landsd_basemap.py`, then run
`python scripts/register_basemap_sources.py`. The supplied 2026-07-24 eSUA/RFZ
archive is clipped into each case and hash-pinned; its redistribution terms
remain an explicit publication blocker until confirmed. Run `pytest tests` for
source, lifecycle, and evaluator mutation tests.

The three tasks use an explicit 2 km mission-corridor `planning_extent`. The
whole-Hong-Kong DTM is retained only in the ignored `.source-cache` during task
authoring; distributed DEM, building, census, weather, and RFZ layers are clipped
to each task extent. The offline topographic packs use an additional 20% visual
padding. Basemap content outside the declared extent is not planning/scoring data.

After the Ubuntu/Python 3.12 wheelhouse has been built, run
`python scripts/stage_release.py`. It produces the ALE-native split layout under
`dist/ale-v0.2`: task code in `tasks/transport_safety/` and staged
`input/software/reference` payloads in
`task_data/transport_safety/<task>/base/`. The reference subtree is for ALE's
post-run hidden-reference staging and must never be mounted during agent work.
