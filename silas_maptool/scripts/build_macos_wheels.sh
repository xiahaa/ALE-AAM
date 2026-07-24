#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BUILD_PYTHON=${PYTHON_BIN:-python3}
ARCH=$(uname -m)

case "$ARCH" in
  arm64|x86_64) ;;
  *)
    echo "Unsupported macOS architecture: $ARCH (expected arm64 or x86_64)." >&2
    exit 2
    ;;
esac

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This maintenance script must run on macOS." >&2
  exit 2
fi

if ! command -v xcrun >/dev/null 2>&1 || ! xcrun --find clang >/dev/null 2>&1; then
  echo "Xcode Command Line Tools are required only on this wheel-builder Mac." >&2
  echo "Install them with: xcode-select --install" >&2
  exit 2
fi

VENV="$ROOT/build/macos-wheel-builder"
"$BUILD_PYTHON" -m venv "$VENV"
PY="$VENV/bin/python"
"$PY" -m pip install --upgrade pip "cibuildwheel==4.1.0"

export CIBW_ARCHS_MACOS="$ARCH"
export CIBW_BUILD=${CIBW_BUILD:-"cp310-* cp311-* cp312-* cp313-*"}
export CIBW_SKIP=${CIBW_SKIP:-""}
export CIBW_TEST_REQUIRES=${CIBW_TEST_REQUIRES:-"pytest httpx jsonschema"}
export CIBW_TEST_COMMAND=${CIBW_TEST_COMMAND:-"python -m silas_maptool doctor --json && silas-maptool inspect --scenario {project}/sample_scenario --json && silas-maptool plan-all --scenario {project}/sample_scenario --outdir {project}/wheel-test-output && python {project}/scripts/wheel_smoke.py {project}/sample_scenario {project}/wheel-test-output && python -m pytest {project}/tests"}

OUT="$ROOT/dist/macos-$ARCH"
mkdir -p "$OUT"
"$PY" -m cibuildwheel --platform macos --output-dir "$OUT" "$ROOT"

echo "Built macOS $ARCH wheels:"
find "$OUT" -maxdepth 1 -type f -name 'silas_maptool-*.whl' -print
