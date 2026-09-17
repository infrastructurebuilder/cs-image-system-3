# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""stage 16: the Justfile's contract.  Five reserved targets in lifecycle
order (`init`, `build`, `test`, `full-test`, `release`), listed first;
`build` wraps `uv build`; `full-test` runs the slow legs and reports a
missing prerequisite as SKIPPED; `release` is gated on `full-test`; and the
`preflight` command that gates full-test's cloud-reading legs reads the
credential caches without loading the configuration."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from v2_support import FIXTURE_CONFIG

REPO = Path(__file__).resolve().parents[1]
CONTRACT = ["init", "build", "test", "full-test", "release"]


def _recipes() -> dict[str, tuple[str, str]]:
    """name -> (dependency text, body) in file order, from the Justfile source."""
    out: dict[str, tuple[str, str]] = {}
    lines = (REPO / "Justfile").read_text().splitlines()
    i = 0
    header = re.compile(r"^([A-Za-z_][\w-]*)((?:\s+\*?[\w-]+(?:=\"[^\"]*\")?)*)\s*:(?!=)\s*(.*)$")   # `*ARGS` too
    while i < len(lines):
        m = header.match(lines[i])
        if m and not lines[i].startswith(("set ", "export ", "#")):
            name, deps = m.group(1), m.group(3)
            body: list[str] = []
            i += 1
            while i < len(lines) and (lines[i].startswith(("\t", " ")) or not lines[i].strip()):
                body.append(lines[i])
                i += 1
            out[name] = (deps, "\n".join(body))
            continue
        i += 1
    assert out
    return out


def test_the_five_contract_targets_come_first_in_lifecycle_order():
    listed = [n for n in _recipes() if n != "default"]
    assert listed[:5] == CONTRACT, listed[:8]
    if shutil.which("just"):                                   # what an operator sees from bare `just`
        out = subprocess.run(["just", "--list", "--unsorted"], cwd=REPO, capture_output=True, text=True, check=True).stdout
        shown = [ln.split()[0] for ln in out.splitlines() if ln.startswith("    ") and ln.split()]
        assert shown[:5] == CONTRACT, shown[:8]
        assert "default" not in shown                        # [private]


def test_build_wraps_uv_build_and_the_gates_hold():
    r = _recipes()
    assert "uv build --all-packages" in r["build"][1]
    assert "pytest" in r["test"][0] and "lint" in r["test"][0] and "typecheck" in r["test"][0]
    assert r["verify"][0].split() == ["test"]                 # the alias
    deps, body = r["full-test"]
    assert deps.split() == ["test"]
    for needle in ("just test-mods --strict", "just preflight", "run --all", "state query --strict", "cs-image-system-3/tfmodules"):
        assert needle in body, needle
    assert body.count("SKIPPED") >= 2                         # docker leg, credential legs
    deps, body = r["release"]
    assert "full-test" in deps.split()
    for needle in ("git status --porcelain", "mod-tests.yaml", "uv version", "git tag -a", "just build", "uv publish", "UV_PUBLISH_URL", "SKIPPED"):
        assert needle in body, needle
    assert "git push" not in body.replace("push with: git push", "")   # nothing is pushed by the recipe


def _closure(recipes: dict[str, tuple[str, str]], name: str) -> set[str]:
    """The recipe plus every recipe in its dependency chain."""
    seen: set[str] = set()
    todo = [name]
    while todo:
        n = todo.pop()
        if n in seen or n not in recipes:
            continue
        seen.add(n)
        todo += [d for d in re.findall(r"[A-Za-z_][\w-]*", recipes[n][0]) if d in recipes]
    return seen


def test_the_live_configuration_never_reaches_the_fast_suite_and_is_guarded_elsewhere():
    """Stage 28: `just test` needs no live configuration (the tests own the
    frozen fixture), and every recipe that drives one is guarded -- by
    config-guard in its dependency chain, or an inline check of
    cfg/_config.yml (full-test, whose SKIPPED line names the reason)."""
    r = _recipes()
    assert "config_root" not in r["test"][1] and "config_root" not in r["init"][1]
    for n in _closure(r, "test") | _closure(r, "init") | _closure(r, "build"):
        assert "{{config_root}}" not in r[n][1] and "{{gce_cli}}" not in r[n][1], n
    drivers = {n for n, (_, body) in r.items() if "{{config_root}}" in body or "{{gce_cli}}" in body}
    assert drivers >= {"cli", "v2-dry-run", "test-mods", "preflight", "cloud-preflight", "full-test", "release"}
    for n in drivers - {"config-guard"}:
        closure = _closure(r, n)
        inline = any("cfg/_config.yml" in r[m][1] for m in closure)
        assert "config-guard" in closure or inline, n
    assert "exit 2" in r["config-guard"][1] and "tests/fixtures/config" in r["config-guard"][1]
    # config-drift: the committed emission versus a fresh dry run, run-local noise ignored
    deps, body = r["config-drift"]
    assert "config-guard" in deps.split()
    normaliser = (REPO / "scripts" / "normalise-emission").read_text()      # stage 45: the normaliser is a shared script
    for needle in ("git -C", "archive HEAD generated", "run --all", "scripts/normalise-emission", "diff -r", "exit 1"):
        assert needle in body, needle
    for needle in ("<RUN>", "<STAMP>", "run-summary.json", "state-report.json", ".terraform.lock.hcl"):
        assert needle in normaliser, needle
    assert "<ROOT>" not in body + normaliser and "s#--root-dir" not in body + normaliser   # stage 38: an absolute path in the emission IS drift
    assert not re.search(r"cs-image-system .*--commit", body)   # it never records anything
    assert "--undeclare instance:gce-test" in r["gce-decommission"][1] and "--overlay" not in r["gce-decommission"][1]


# ------------------------------------------------------------- preflight

def _preflight(monkeypatch, **env: str):
    from typer.testing import CliRunner
    from cs_image_system.system.cli import app
    for var in ("AWS_PROFILE", "AWS_ACCESS_KEY_ID"):
        monkeypatch.delenv(var, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return CliRunner().invoke(app, ["--root-dir", str(FIXTURE_CONFIG), "preflight"])


def test_preflight_reports_absent_sessions_and_exits_2(monkeypatch):
    # conftest: an empty AWS dir, no ADC -- every session absent
    result = _preflight(monkeypatch)
    assert result.exit_code == 2, result.output
    assert "aws-east2-runtime" in result.output and "gcloud-east1" in result.output
    assert "not in" in result.output or "no SSO token" in result.output      # the aws line's reason
    assert "no Application Default Credentials" in result.output
    assert "cannot load" in result.output


def test_preflight_passes_with_static_keys_and_an_adc(monkeypatch, tmp_path):
    adc = tmp_path / "adc.json"
    adc.write_text(json.dumps({"type": "authorized_user"}))
    result = _preflight(monkeypatch, AWS_ACCESS_KEY_ID="AKIA-test", GOOGLE_APPLICATION_CREDENTIALS=str(adc))
    assert result.exit_code == 0, result.output
    assert "env keys" in result.output and "ADC authorized_user" in result.output
    assert "every session present" in result.output


def test_preflight_fails_on_a_credential_that_is_set_but_empty(monkeypatch, tmp_path):
    """stage 43: a secret set from a checkout missing its source file passed three
    green CI jobs that ran nothing -- the variable existed and its value was "".
    Set-but-empty is a failure, reported by NAME, never by value."""
    from cs_image_system.base.commands.preflight import empty_environment_credentials
    assert empty_environment_credentials({"TF_VAR_X": "", "OKTA_API_TOKEN": "", "AWS_PROFILE": "p", "HOME": ""}) == \
        ["OKTA_API_TOKEN", "TF_VAR_X"]
    adc = tmp_path / "adc.json"
    adc.write_text(json.dumps({"type": "authorized_user"}))
    result = _preflight(monkeypatch, AWS_ACCESS_KEY_ID="AKIA-test", GOOGLE_APPLICATION_CREDENTIALS=str(adc),
                        TF_VAR_NOS_KEY="")
    assert result.exit_code == 2, result.output
    assert "TF_VAR_NOS_KEY is set but EMPTY" in result.output and "AKIA-test" not in result.output


def test_the_looser_ci_recipe_is_gone_and_the_tofu_executing_recipes_take_the_lock():
    r = _recipes()
    assert "ci" not in r, "`just ci` (pyright non-blocking) must not return: `just test` is the bar"
    for name in ("cloud-bake", "cloud-cycle", "cloud-launch", "gce-decommission", "v2-dry-run"):
        assert "scripts/with-tofu-lock" in r[name][1], name              # may execute the roots
    for name in ("config-drift", "cloud-preflight", "test", "pytest", "golden-regen"):
        assert "with-tofu-lock" not in r[name][1], f"{name} never starts tofu and must not contend"


def test_the_performing_recipe_and_the_runtime_guard_hold_their_shape():
    """stage 45: `cloud-perform` is the one recipe that executes a runtime's
    bakes, releases and retention from CI; it is scoped to the runtime, real,
    committed and locked. `runtime-unchanged` compares a runtime's emission
    across records with the same normaliser config-drift uses."""
    r = _recipes()
    body = r["cloud-perform"][1]
    for needle in ("scripts/with-tofu-lock", "--no-dry-run", "run base-image instance-image release retention",
                   "--only-runtime {{runtime}}", "--commit"):
        assert needle in body, needle
    assert "--apply-runtime" not in body and "--all" not in body       # bakes, releases, retention: roots plan and gate only
    assert "cloud-preflight" in r["cloud-perform"][0]
    guard = r["runtime-unchanged"][1]
    assert "runtime describe" in guard and "scripts/normalise-emission" in guard and "git -C" in guard
    assert "scripts/normalise-emission" in r["config-drift"][1]
    script = REPO / "scripts" / "normalise-emission"
    assert os.access(script, os.X_OK)
    text = script.read_text()
    assert "run-summary.json" in text and "[0-9]{8}[-_][0-9]{6}" in text


def test_preflight_readiness_marks_presence():
    from cs_image_system.base.commands.preflight import SessionInfo, _merge
    a = SessionInfo("r1", "aws", "profile p", None, "no SSO token cached", present=False)
    b = SessionInfo("r2", "aws", "profile p", None, "no SSO token cached", present=False)
    merged = _merge([a, b])
    assert len(merged) == 1 and merged[0].runtime == "r1, r2" and merged[0].present is False
    assert os.environ.get("CSIS_AWS_DIR")                     # the suite never reads the real caches
