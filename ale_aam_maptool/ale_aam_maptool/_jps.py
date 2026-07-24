"""Load the wheel-bundled native extension without process-wide I/O changes."""
from __future__ import annotations

import importlib
import importlib.metadata
import os
import sys
from pathlib import Path

_LOADED = None


def load_jps():
    global _LOADED
    if _LOADED is not None:
        return _LOADED
    errors = []
    for name in ("ale_aam_maptool.jps_planner_bindings", "jps_planner_bindings"):
        try:
            _LOADED = importlib.import_module(name)
            return _LOADED
        except ImportError as exc:
            errors.append(str(exc))
    override = os.environ.get("ALE_AAM_JPS_LIB")
    directories = [Path(override).resolve()] if override else []
    try:
        # A source checkout can shadow an installed wheel during tests. Locate
        # the wheel's extension explicitly without relying on cwd/sys.path.
        directories.append(Path(importlib.metadata.distribution("ale-aam-maptool").locate_file("ale_aam_maptool")).resolve())
    except importlib.metadata.PackageNotFoundError:
        pass
    for directory in dict.fromkeys(directories):
        if directory.is_dir():
            sys.path.insert(0, str(directory))
            try:
                _LOADED = importlib.import_module("jps_planner_bindings")
                return _LOADED
            except ImportError as exc:
                errors.append(str(exc))
            finally:
                if sys.path[0] == str(directory):
                    sys.path.pop(0)
    raise ImportError(
        "native JPS backend is unavailable; install a wheel matching this "
        "Python/platform (source compilation is not required for users). "
        + "; ".join(errors[-2:])
    )


def backend_info() -> dict:
    try:
        module = load_jps()
        return {"available": True, "module": module.__name__, "api_version": getattr(module, "API_VERSION", "1")}
    except Exception as exc:
        return {"available": False, "error": str(exc)}
