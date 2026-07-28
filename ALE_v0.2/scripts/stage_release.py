"""Build one self-contained ALE upload directory and ZIP per task.

Each archive contains exactly one task ID with its ``base`` data variant.  Input,
software, and reference remain sibling payloads so ALE can keep reference hidden
until evaluation.  The final public map tool has no automatic planning feature.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASKS = (
    "urban_drone_logistics",
    "cross_sea_drone_logistics",
    "emergency_blood_transport",
)
DOMAIN = "transport_safety"
TOOL_VERSION = "1.0.0"
REQUIRED_RUNTIME_DISTS = {
    "fastapi",
    "numpy",
    "pillow",
    "pydantic",
    "pyproj",
    "rasterio",
    "shapely",
    "typer",
    "uvicorn",
}


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


def validate_wheelhouse(wheelhouse: Path) -> list[Path]:
    wheels = sorted(wheelhouse.glob("*.whl"))
    tool = [path for path in wheels if path.name.startswith(f"ale_aam_maptool-{TOOL_VERSION}-")]
    if len(tool) != 1:
        raise RuntimeError(
            f"wheelhouse must contain exactly one ale-aam-maptool {TOOL_VERSION} wheel"
        )
    if not tool[0].name.endswith("-py3-none-any.whl"):
        raise RuntimeError("the final ale-aam-maptool wheel must be the universal py3-none-any build")
    distributions = {
        path.name.split("-", 1)[0].lower().replace("_", "-") for path in wheels
    }
    missing = sorted(REQUIRED_RUNTIME_DISTS - distributions)
    if missing:
        raise RuntimeError(
            "wheelhouse is incomplete; missing direct runtime wheels: " + ", ".join(missing)
        )
    return wheels


def write_manifest(package: Path, task: str) -> Path:
    files = sorted(path for path in package.rglob("*") if path.is_file())
    manifest = {
        "schema_version": "1.0",
        "tool_version": TOOL_VERSION,
        "automatic_planning": False,
        "domain": DOMAIN,
        "task": task,
        "variant": "base",
        "files": [
            {
                "path": path.relative_to(package).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in files
        ],
    }
    target = package / "release_manifest.json"
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def deterministic_zip(package: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in package.rglob("*") if item.is_file()):
            info = zipfile.ZipInfo(path.relative_to(package).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def stage_task(output: Path, wheels: list[Path], task: str) -> dict:
    source = ROOT / task
    package = output / task
    code = package / "tasks" / DOMAIN / task
    code.mkdir(parents=True)
    shutil.copy2(source / "main.py", code / "main.py")
    shutil.copy2(source / "task_card.json", code / "task_card.json")
    private = package / "tasks" / DOMAIN / "_private"
    private.mkdir()
    shutil.copy2(ROOT / "_private" / "evaluator.py", private / "evaluator.py")

    payload = package / "task_data" / DOMAIN / task / "base"
    copy_tree(source / "input", payload / "input")
    copy_tree(source / "reference", payload / "reference")
    staged_wheels = payload / "software" / "wheelhouse"
    staged_wheels.mkdir(parents=True)
    for wheel in wheels:
        shutil.copy2(wheel, staged_wheels / wheel.name)

    write_manifest(package, task)
    archive = output / f"ale-aam-{task}-base.zip"
    deterministic_zip(package, archive)
    return {
        "task": task,
        "variant": "base",
        "directory": str(package),
        "archive": str(archive),
        "archive_size": archive.stat().st_size,
        "archive_sha256": sha256(archive),
    }


def stage(output: Path, wheelhouse: Path, selected: list[str] | None = None) -> list[dict]:
    if output.exists():
        raise FileExistsError(f"release target already exists: {output}")
    wheels = validate_wheelhouse(wheelhouse)
    tasks = selected or list(TASKS)
    unknown = sorted(set(tasks) - set(TASKS))
    if unknown:
        raise ValueError("unknown task ID(s): " + ", ".join(unknown))
    if len(tasks) != len(set(tasks)):
        raise ValueError("each task may be staged only once")
    output.mkdir(parents=True)
    packages = [stage_task(output, wheels, task) for task in tasks]
    index = {
        "schema_version": "1.0",
        "tool_version": TOOL_VERSION,
        "automatic_planning": False,
        "packages": packages,
    }
    (output / "release_index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return packages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "ale-aam-final")
    parser.add_argument(
        "--wheelhouse", type=Path, default=ROOT.parent / "ale_aam_maptool" / "wheelhouse"
    )
    parser.add_argument("--task", action="append", choices=TASKS,
                        help="Stage only this task; repeat as needed. Defaults to all three.")
    args = parser.parse_args()
    packages = stage(args.out.resolve(), args.wheelhouse.resolve(), args.task)
    print(json.dumps({"ok": True, "packages": packages}, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
