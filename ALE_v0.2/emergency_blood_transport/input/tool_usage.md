# Tool use (offline)

The staged `software/wheelhouse/` contains wheels. `start()` installs them into
`software/.venv` with `--no-index --only-binary=:all:`. Use
`software/.venv/bin/silas-maptool doctor --json`, `inspect`, `plan-all`, `grid`,
and `validate`. Do not use network access, sudo, apt, Homebrew, MSVC, or a source
compiler. The web demo is `serve --scenario input/gis --host 127.0.0.1`.
