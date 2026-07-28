#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}
"$PYTHON_BIN" -m venv "$ROOT/.venv"
PY="$ROOT/.venv/bin/python"
PICK="$ROOT/.venv/wheel-select"
mkdir -p "$PICK"
find "$PICK" -maxdepth 1 -type f -name 'ale_aam_maptool-*.whl' -delete
set --
for directory in "$ROOT/wheelhouse" "$ROOT/dist" "$ROOT"/dist/*; do
  if [ -d "$directory" ]; then set -- "$@" --find-links "$directory"; fi
done
if [ "$#" -eq 0 ]; then
  echo "No wheel directory found. Put a compatible release wheel in wheelhouse/ or dist/." >&2
  exit 2
fi
if ! "$PY" -m pip download --no-deps --no-index "$@" --dest "$PICK" ale-aam-maptool; then
  PY_TAG=$($PY -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")')
  PLATFORM=$($PY -c 'import platform; print(f"{platform.system()} {platform.machine()}")')
  echo "No compatible ale-aam-maptool wheel was found for $PY_TAG on $PLATFORM." >&2
  echo "Download the matching prebuilt wheel and place it under dist/, then rerun install.sh." >&2
  echo "macOS artifacts are named ale-aam-maptool-0.2.1-macos-wheels in the wheel CI." >&2
  exit 2
fi
WHEEL=$(find "$PICK" -maxdepth 1 -type f -name 'ale_aam_maptool-*.whl' -print -quit)
if [ -z "$WHEEL" ]; then
  echo "Wheel selection completed without producing a ale-aam-maptool wheel." >&2
  exit 2
fi
if [ -f "$ROOT/wheelhouse/$(basename "$WHEEL")" ]; then
  "$PY" -m pip install --no-index --find-links "$ROOT/wheelhouse" "$WHEEL"
else
  "$PY" -m pip install "$WHEEL"
fi
"$PY" -m ale_aam_maptool doctor --json
