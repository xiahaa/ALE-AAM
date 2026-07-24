"""Stage ALE task code and task-data payloads in the official directory shape.

The generated tree deliberately keeps ``reference`` out of ``input``. ALE's
deployer exposes input/software before the agent run and stages reference only
after the run has completed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASKS = (
    "urban_drone_logistics",
    "cross_sea_drone_logistics",
    "emergency_blood_transport",
)
DOMAIN = "transport_safety"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_tree(source: Path, target: Path) -> None:
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )


def stage(output: Path, wheelhouse: Path) -> Path:
    if output.exists():
        raise FileExistsError(f"release target already exists: {output}")
    wheels = sorted(wheelhouse.glob("*.whl"))
    native = [p for p in wheels if p.name.startswith("ale_aam_maptool-0.2.0-cp312-") and "linux" in p.name]
    if len(native) != 1:
        raise RuntimeError("wheelhouse must contain exactly one Linux CPython 3.12 ale-aam-maptool 0.2.0 wheel")

    tasks_root = output / "tasks" / DOMAIN
    data_root = output / "task_data" / DOMAIN
    tasks_root.mkdir(parents=True)
    (tasks_root / "_private").mkdir()
    shutil.copy2(ROOT / "_private" / "evaluator.py", tasks_root / "_private" / "evaluator.py")

    for task in TASKS:
        source = ROOT / task
        code = tasks_root / task
        code.mkdir()
        shutil.copy2(source / "main.py", code / "main.py")
        shutil.copy2(source / "task_card.json", code / "task_card.json")

        payload = data_root / task / "base"
        copy_tree(source / "input", payload / "input")
        copy_tree(source / "reference", payload / "reference")
        staged_wheels = payload / "software" / "wheelhouse"
        staged_wheels.mkdir(parents=True)
        for wheel in wheels:
            shutil.copy2(wheel, staged_wheels / wheel.name)

    files = sorted(p for p in output.rglob("*") if p.is_file())
    manifest = {
        "schema_version": "1.0",
        "tool_version": "0.2.0",
        "domain": DOMAIN,
        "tasks": list(TASKS),
        "files": [
            {"path": p.relative_to(output).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)}
            for p in files
        ],
    }
    (output / "release_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "ale-v0.2")
    parser.add_argument("--wheelhouse", type=Path, default=ROOT.parent / "ale_aam_maptool" / "wheelhouse")
    args = parser.parse_args()
    print(stage(args.out.resolve(), args.wheelhouse.resolve()))


if __name__ == "__main__":
    main()
