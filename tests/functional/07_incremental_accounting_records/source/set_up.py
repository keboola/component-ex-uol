"""Restore the input state after datadirtest setUp() clears it.

datadirtest always calls _override_input_state({}) in setUp which resets
in/state.json to {}.  This set_up.py runs AFTER that and restores the
watermark so the component reads the correct last_run and sends date_from
to the API (which is what the VCR cassette was recorded against).
"""

import json
from pathlib import Path


def run(context):
    state_path = Path(context.data_dir) / "source" / "data" / "in" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w") as f:
        json.dump({"last_run": "2026-02-01T00:00:00+00:00"}, f)
