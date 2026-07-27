"""Live integration tests against a real Radarr instance.

Skipped unless ``CONFIGARR_IT_RADARR_URL`` and ``CONFIGARR_IT_RADARR_KEY`` are set,
so the normal (mocked) suite and ``nix flake check`` are unaffected. The CI
``integration`` workflow starts a throwaway Radarr container and points these at it;
run them locally the same way (see ``docs``).

They exercise the real create → idempotent → prune → recreate round-trip end to end,
which the mocked suite can't: it catches *arr API drift and packaging regressions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from configarr.config import parse_config
from configarr.runner import run_apply, run_plan

URL = os.environ.get("CONFIGARR_IT_RADARR_URL")
KEY = os.environ.get("CONFIGARR_IT_RADARR_KEY")

pytestmark = pytest.mark.skipif(
    not (URL and KEY),
    reason="set CONFIGARR_IT_RADARR_URL and CONFIGARR_IT_RADARR_KEY to run live tests",
)

# A uniquely-named custom format so the test never touches a real one.
CF = "configarr-integration-test-cf"


def _config(tmp_path: Path, *, include_cf: bool) -> Path:
    body = (
        f"radarr:\n  instances:\n    it:\n      base_url: {URL}\n      api_key: {KEY}\n"
    )
    if include_cf:
        body += (
            "      custom_formats:\n        definitions:\n"
            f"          {CF}:\n            specifications:\n"
            "              - name: x265\n"
            "                implementation: ReleaseTitleSpecification\n"
            '                fields:\n                  value: "(x|h)265"\n'
        )
    # Distinct filenames so the with-CF and without-CF configs don't overwrite
    # each other (they share the explicit state file passed to run_apply).
    p = tmp_path / ("with-cf.yml" if include_cf else "without-cf.yml")
    p.write_text(body)
    return p


def _plan_ops(cfg: Path) -> dict[str, str]:
    doc = json.loads(run_plan(parse_config(cfg), output="json"))
    ops: dict[str, str] = {}
    for provider in doc["providers"]:
        for resource in provider["resources"]:
            ops[str(resource["key"])] = resource["op"]
    return ops


def test_check_passes(tmp_path):
    # --check reaches nothing, but the URL/key must parse and the config validate.
    from click.testing import CliRunner

    from configarr.__main__ import main

    res = CliRunner().invoke(
        main, ["--config", str(_config(tmp_path, include_cf=True)), "--check"]
    )
    assert res.exit_code == 0, res.output


def test_custom_format_roundtrip(tmp_path):
    state = tmp_path / ".configarr-state.json"
    cfg_with = _config(tmp_path, include_cf=True)

    # 1. The CF is not there yet -> a create.
    assert _plan_ops(cfg_with).get(CF) == "create"

    # 2. Apply, then re-plan: it exists and matches -> no longer in the plan.
    run_apply(parse_config(cfg_with), state_path=state)
    assert CF not in _plan_ops(cfg_with)

    # 3. Drop it from config and prune: ownership state lets prune delete it.
    cfg_without = _config(tmp_path, include_cf=False)
    run_apply(parse_config(cfg_without), prune=True, state_path=state)

    # 4. It's gone again -> a create.
    assert _plan_ops(cfg_with).get(CF) == "create"
