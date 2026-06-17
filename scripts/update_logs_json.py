"""Update cassettes/logs.json for all functional tests by replaying with the
existing HTTP cassette and saving the newly captured logs.

This is the correct way to regenerate logs.json after a log-output change
(e.g. streaming refactor that removed "Fetched N records" lines).  HTTP
cassettes (requests.json) are left untouched — only logs.json is updated.

Usage:
    uv run python scripts/update_logs_json.py
"""

from __future__ import annotations

import os
import runpy
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUNCTIONAL_DIR = ROOT / "tests" / "functional"
COMPONENT_SCRIPT = ROOT / "src" / "component.py"


def _update_logs_for_test(test_dir: Path, tmp_dir: Path) -> None:
    """Replay one test case and overwrite its logs.json with current output."""
    from keboola.vcr.recorder import (  # noqa: PLC0415
        ComponentRunResult,
        VCRRecorder,
        save_logs,
    )
    from keboola.vcr.sanitizers import DefaultSanitizer  # noqa: PLC0415

    cassette_dir = test_dir / "source" / "data" / "cassettes"
    requests_cassette = cassette_dir / "requests.json"
    if not requests_cassette.exists():
        print(f"  [SKIP] {test_dir.name}: no requests.json")
        return

    # Work on a temp copy so we never pollute source.
    work = tmp_dir / test_dir.name
    shutil.copytree(str(test_dir), str(work))
    source_data = work / "source" / "data"
    for subdir in ["in", "out", "out/tables", "out/files"]:
        (source_data / subdir).mkdir(parents=True, exist_ok=True)

    os.environ["KBC_DATADIR"] = str(source_data)

    # Create an empty state.json (mirrors what TestDataDir._override_input_state does)
    # so the component doesn't log "State file not found. First run?"
    state_path = source_data / "in" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if not state_path.exists():
        state_path.write_text("{}")

    src_dir = str(COMPONENT_SCRIPT.parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    # Build the recorder against the work-copy cassette dir.
    work_cassette_dir = source_data / "cassettes"

    # Load VCR_SANITIZERS defined in component.py.
    import runpy as _rp  # noqa: PLC0415

    _orig_path = sys.path.copy()
    try:
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        _globals = _rp.run_path(str(COMPONENT_SCRIPT), run_name="__vcr_probe__")
        component_sanitizers = _globals.get("VCR_SANITIZERS") or []
    except Exception:
        component_sanitizers = []
    finally:
        sys.path[:] = _orig_path

    sanitizers = component_sanitizers or [DefaultSanitizer()]

    recorder = VCRRecorder(
        cassette_dir=work_cassette_dir,
        sanitizers=sanitizers,
        freeze_time_at="auto",
        record_mode="none",  # never make real HTTP calls
        capture_logs=True,
    )

    # Capture the new logs by monkey-patching _assert_replay_result to
    # save logs instead of asserting.
    captured: list[ComponentRunResult] = []

    def _saving_assert(run_result, stdout_capture):
        if run_result is not None:
            captured.append(run_result)

    original_assert = recorder._assert_replay_result
    recorder._assert_replay_result = _saving_assert  # type: ignore[method-assign]

    def _run_component() -> None:
        runpy.run_path(str(COMPONENT_SCRIPT), run_name="__main__")

    try:
        recorder.replay(_run_component)
    except Exception:
        # Ignore comparison errors; we only care about the captured logs.
        pass
    finally:
        recorder._assert_replay_result = original_assert  # type: ignore[method-assign]

    if not captured:
        print(f"  [WARN] {test_dir.name}: no logs captured — skipping")
        return

    run_result = captured[0]

    # Sanitize and save to the *original* cassette dir.
    from keboola.vcr.recorder import LogSanitizer  # noqa: PLC0415

    real_logs_path = cassette_dir / "logs.json"
    if recorder.secrets:
        run_result = LogSanitizer(recorder.secrets).sanitize(run_result)
    save_logs(run_result, real_logs_path)

    print(f"  [OK] {test_dir.name}: updated logs.json ({len(run_result.logs)} log lines)")


def main() -> None:
    test_cases = sorted(
        d
        for d in FUNCTIONAL_DIR.iterdir()
        if d.is_dir()
        and not d.name.startswith("_")
        and (d / "source" / "data" / "cassettes" / "requests.json").exists()
        and (d / "source" / "data" / "cassettes" / "logs.json").exists()
    )

    print(f"Found {len(test_cases)} test cases with both requests.json and logs.json")
    updated = 0

    with tempfile.TemporaryDirectory(prefix="update_logs_") as tmp:
        tmp_dir = Path(tmp)
        for test_dir in test_cases:
            print(f"  Processing {test_dir.name}...")
            _update_logs_for_test(test_dir, tmp_dir)
            updated += 1

    print(f"\nUpdated logs.json for {updated} test case(s).")


if __name__ == "__main__":
    main()
