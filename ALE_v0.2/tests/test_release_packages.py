import importlib.util
import json
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stage_release.py"


def _module():
    spec = importlib.util.spec_from_file_location("ale_aam_stage_release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_release_staging_outputs_one_self_contained_archive_per_task(tmp_path):
    release = _module()
    source_root = tmp_path / "source"
    (source_root / "_private").mkdir(parents=True)
    (source_root / "_private/evaluator.py").write_text("SCORE = 1\n", encoding="utf-8")
    for task in release.TASKS:
        source = source_root / task
        (source / "input").mkdir(parents=True)
        (source / "reference").mkdir()
        (source / "main.py").write_text("def load(): return []\n", encoding="utf-8")
        (source / "task_card.json").write_text("{}\n", encoding="utf-8")
        (source / "input/task_prompt.md").write_text(task, encoding="utf-8")
        (source / "reference/anchors.json").write_text("{}\n", encoding="utf-8")
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    (wheelhouse / "ale_aam_maptool-1.0.0-py3-none-any.whl").write_bytes(b"tool")
    for dependency in release.REQUIRED_RUNTIME_DISTS:
        filename = dependency.replace("-", "_") + "-1.0.0-py3-none-any.whl"
        (wheelhouse / filename).write_bytes(b"dependency")
    release.ROOT = source_root

    output = tmp_path / "release"
    packages = release.stage(output, wheelhouse)
    assert [item["task"] for item in packages] == list(release.TASKS)
    for item in packages:
        task = item["task"]
        archive = Path(item["archive"])
        with zipfile.ZipFile(archive) as bundle:
            names = set(bundle.namelist())
        prefix = f"task_data/{release.DOMAIN}/{task}/base"
        assert f"tasks/{release.DOMAIN}/{task}/main.py" in names
        assert f"tasks/{release.DOMAIN}/{task}/task_card.json" in names
        assert f"tasks/{release.DOMAIN}/_private/evaluator.py" in names
        assert f"{prefix}/input/task_prompt.md" in names
        assert f"{prefix}/software/wheelhouse/ale_aam_maptool-1.0.0-py3-none-any.whl" in names
        assert f"{prefix}/reference/anchors.json" in names
        assert not any(
            f"/{other}/" in name for other in release.TASKS if other != task for name in names
        )
        manifest = json.loads((Path(item["directory"]) / "release_manifest.json").read_text())
        assert manifest["task"] == task
        assert manifest["variant"] == "base"
        assert manifest["automatic_planning"] is False
