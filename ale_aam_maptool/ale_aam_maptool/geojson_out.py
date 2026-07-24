from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def build_feature(route_name, strategy, objective, coords_lonlat, waypoints, metrics, extra=None):
    properties = {
        "schema_version": "2.0", "route_name": route_name,
        "strategy": strategy, "objective": objective, "waypoints": waypoints,
        "total_distance_m": metrics["total_distance_m"],
        "estimated_duration_s": metrics["estimated_duration_s"],
        "estimated_energy_wh": metrics["estimated_energy_wh"],
    }
    properties.update(extra or {})
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[round(float(lo), 7), round(float(la), 7)] for lo, la in coords_lonlat]},
        "properties": properties,
    }


def write_json_atomic(data, path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        try: os.unlink(temporary)
        except OSError: pass
        raise
    return target


write_feature = write_json_atomic
