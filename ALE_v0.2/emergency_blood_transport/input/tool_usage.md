# Tool use (offline)

The staged `software/wheelhouse/` contains wheels. `start()` installs them into
`software/.venv` with `--no-index --only-binary=:all:`. Use
`software/.venv/bin/ale-aam-maptool doctor --json`, `inspect`, `plan-all`, `grid`,
and `validate`. Do not use network access, sudo, apt, Homebrew, MSVC, or a source
compiler. The web demo is `serve --scenario input/gis --host 127.0.0.1`.
`input/gis/basemaps/hong_kong_landsd.mbtiles` is visual context only. Derive
constraints and risk from the declared DEM, vector, population, and weather
layers inside `task.json.planning_extent`; do not treat cartographic basemap
pixels, including the 20% frame outside that extent, as scoring truth.
