"""Regenerate expected/ outputs by replaying VCR cassettes.

Runs the component in VCR replay mode for every functional test case that has
cassettes, then copies the actual out/tables/ output to expected/data/out/tables/.

Usage:
    uv run python scripts/regenerate_expected.py
"""

from __future__ import annotations

import json
import os
import re
import runpy
import shutil
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
FUNCTIONAL_DIR = ROOT / "tests" / "functional"
COMPONENT_SCRIPT = ROOT / "src" / "component.py"


def _apply_env_variables(config_path: Path) -> None:
    """Substitute {{env.VAR}} placeholders in config.json."""
    pattern = r"({{env.(.+)}})"
    text = config_path.read_text()
    for full_match, var_name in re.findall(pattern, text):
        value = os.getenv(var_name)
        if not value:
            raise ValueError(f"Environment variable {var_name!r} missing")
        text = text.replace(full_match, value)
    config_path.write_text(json.dumps(json.loads(text)))


def _run_replay(test_dir: Path, tmp_dir: Path) -> None:
    """Run the component in VCR replay mode for one test case."""
    from keboola.vcr.recorder import VCRRecorder  # noqa: PLC0415

    # Copy entire test dir into a temp working copy so we don't pollute source.
    work = tmp_dir / test_dir.name
    shutil.copytree(str(test_dir), str(work))

    source_data = work / "source" / "data"

    # Ensure required dirs exist.
    for subdir in ["in", "out", "out/tables", "out/files"]:
        (source_data / subdir).mkdir(parents=True, exist_ok=True)

    # Apply env variable substitution if needed.
    cfg_path = source_data / "config.json"
    if cfg_path.exists():
        _apply_env_variables(cfg_path)

    os.environ["KBC_DATADIR"] = str(source_data)

    # Suppress ComponentBase's own VCR layer so only ours runs.
    component_base_cls = None
    original_should_replay = None
    try:
        from keboola.component.base import ComponentBase  # noqa: PLC0415

        if hasattr(ComponentBase, "_should_vcr_replay"):
            component_base_cls = ComponentBase
            original_should_replay = ComponentBase._should_vcr_replay
            # Intentional monkeypatch of a class method for the duration of the replay.
            ComponentBase._should_vcr_replay = staticmethod(lambda: False)  # ty: ignore[invalid-assignment]
    except ImportError:
        pass

    # Build VCR recorder from cassettes dir.
    script_dir = str(COMPONENT_SCRIPT.resolve().parent.parent) + "/"
    log_normalizers = [(re.escape(script_dir), "")]

    recorder = VCRRecorder.from_test_dir(
        test_data_dir=source_data,
        freeze_time_at="auto",
        sanitizers=None,
        db_adapters=[],
        log_normalizers=log_normalizers,
    )

    src_dir = str(COMPONENT_SCRIPT.parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    def _run_component() -> None:
        runpy.run_path(str(COMPONENT_SCRIPT), run_name="__main__")

    try:
        recorder.replay(_run_component)
    finally:
        if component_base_cls is not None:
            component_base_cls._should_vcr_replay = original_should_replay  # ty: ignore[invalid-assignment]

    # Copy actual output → expected/
    actual_tables = source_data / "out" / "tables"
    expected_tables = test_dir / "expected" / "data" / "out" / "tables"
    expected_tables.mkdir(parents=True, exist_ok=True)

    # Remove stale files.
    for f in expected_tables.iterdir():
        f.unlink()

    # Copy new output.
    for f in actual_tables.iterdir():
        shutil.copy2(str(f), str(expected_tables / f.name))

    print(f"  [OK] {test_dir.name}: copied {len(list(actual_tables.iterdir()))} file(s)")


def main() -> None:
    test_cases = sorted(
        d
        for d in FUNCTIONAL_DIR.iterdir()
        if d.is_dir()
        and not d.name.startswith("_")
        and (d / "source" / "data" / "cassettes" / "requests.json").exists()
    )

    # Only process cases that actually have table output (i.e. have cassettes
    # with HTTP responses — sync-action-only tests have no table output).
    regenerated = 0

    with tempfile.TemporaryDirectory(prefix="regen_expected_") as tmp:
        tmp_dir = Path(tmp)
        for test_dir in test_cases:
            # Skip cases with no expected/data/out/tables directory or that
            # don't produce table output (sync actions / auth failures).
            expected_tables = test_dir / "expected" / "data" / "out" / "tables"
            if not expected_tables.exists():
                print(f"  [SKIP] {test_dir.name}: no expected/data/out/tables/")
                continue

            print(f"  Regenerating {test_dir.name}...")
            _run_replay(test_dir, tmp_dir)
            regenerated += 1

    print(f"\nRegenerated {regenerated} test case(s).")


if __name__ == "__main__":
    main()
