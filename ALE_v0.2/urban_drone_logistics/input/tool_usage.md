# Tool use (offline)

The staged `software/wheelhouse/` contains wheels. `start()` installs them into
`software/.venv` with `--no-index --only-binary=:all:`. Use
`software/.venv/bin/ale-aam-maptool doctor --json`, `inspect`, `validate`, and
`serve --scenario input/gis --host 127.0.0.1`. Automatic planning is deliberately
disabled. Construct the three routes from the supplied GIS and explicit task
constraints; the local Web UI may be used for manual waypoint editing and GeoJSON
export. Do not use network access, sudo, apt, Homebrew, MSVC, or a source compiler.
`input/gis/basemaps/hong_kong_landsd.mbtiles` is visual context only. Derive
constraints and risk from the declared DEM, vector, population, and weather
layers inside `task.json.planning_extent`; do not treat cartographic basemap
pixels, including the 20% frame outside that extent, as scoring truth.
