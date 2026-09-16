# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Run scoping safe by construction (stage 12).

* `--apply-runtime <rt>` implies the bake filter: images on other
  runtimes read `skip: outside the apply scope` in the bake plan;
* a run whose apply scope is a proper subset of the runtimes (a
  list-valued apply flag or --apply-runtime) REFUSES under --no-dry-run
  when its plan would still bake outside that scope -- before any bake --
  unless the operator allowed it or selected images explicitly; a dry
  run warns; a run with no scope at all is untouched;
* the preflight reads the credential caches (never a value) and reports
  each runtime's session against the expected run length; a strict
  preflight refuses on a session that will not outlast the run.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.v2_support import V2Run, copy_config

GCE = "gcloud-east1"
AWS = "aws-east2-runtime"


def _fresh_copy(tmp_path: Path) -> Path:
    """A config copy with no lineage: every image needs a bake."""
    root = copy_config(tmp_path)
    for f in ("lineage.yaml", "pins.yaml"):
        (root / "meta-state" / f).unlink(missing_ok=True)
    return root


@pytest.fixture
def fresh(tmp_path: Path, monkeypatch):
    root = _fresh_copy(tmp_path)
    runs: list[V2Run] = []

    def make(**kw) -> V2Run:
        run = V2Run(tmp_path, monkeypatch, config_root=root, **kw)
        runs.append(run)
        return run
    try:
        yield make
    finally:
        for r in runs:
            r.restore_cwd()


def _cli_scope(run: V2Run, runtime: str) -> list[str]:
    """What `run --apply-runtime <rt>` does before run_lifecycles (the CLI's
    implied filter), as the harness has no CLI."""
    from cs_image_system.base.commands.runtime_facts import images_on_runtime
    run.ctx.apply_runtime = runtime
    for key in ("apply_storage", "apply_instances"):
        run.ctx.config[key] = [runtime]
    run.ctx.implied_scope = runtime
    return [f"{img}@{runtime}" for img in images_on_runtime(run.ctx, runtime)] or ["none"]


def test_apply_runtime_implies_the_bake_filter_and_the_plan_says_so(fresh):
    run = make = fresh()
    only = _cli_scope(run, GCE)
    summary = run.run(["base-image", "instance-image"], apply=False, only=only)
    assert summary.ok, summary.error
    plan = summary.bake_plan
    assert all(v.startswith("bake:") for k, v in plan.items() if k.endswith(f"@{GCE}"))
    aws = {k: v for k, v in plan.items() if k.endswith(f"@{AWS}")}
    assert aws and all(v == f"skip: outside the apply scope (--apply-runtime {GCE})" for v in aws.values())
    files = [str(p.relative_to(run.generated)) for p in run.generated.rglob("*source-*.pkr.hcl")]
    assert files and all("pckr-gce" in f for f in files)          # no AWS bake surface at all


def test_a_scoped_run_refuses_bakes_outside_its_scope_before_any_bake(fresh):
    from cs_image_system.base.commands.run_scope import apply_scope_runtimes, unscoped_bakes
    run = fresh(dry_run=False)
    run.ctx.config["apply_instances"] = [GCE]                   # the gce-apply overlay's shape, no --only
    assert apply_scope_runtimes(run.ctx) == {GCE}
    summary = run.run(["base-image"], apply=False)
    assert not summary.ok
    assert "run scope: bake(s) outside the apply scope ['gcloud-east1']" in str(summary.error)
    assert f"basic-rh-10@{AWS}" in str(summary.error) and "--allow-unscoped-bakes" in str(summary.error)
    assert unscoped_bakes(run.ctx, summary.bake_plan) == sorted(
        k for k, v in summary.bake_plan.items() if v.startswith("bake:") and k.endswith(f"@{AWS}"))
    assert not list(run.generated.rglob("*.pkr.hcl"))            # nothing generated, nothing baked


def test_the_operator_may_allow_or_select_explicitly_and_a_dry_run_only_warns(fresh, caplog):
    run = fresh(dry_run=False)
    run.ctx.config["apply_instances"] = [GCE]
    run.ctx.allow_unscoped_bakes = True
    assert run.run(["base-image"], apply=False).ok
    run = fresh(dry_run=False)
    run.ctx.config["apply_instances"] = [GCE]
    run.ctx.explicit_bake_selection = True                        # --only / --only-runtime was given
    assert run.run(["base-image"], apply=False, only=[f"basic-rh-10@{AWS}"]).ok
    run = fresh()                                                 # dry run
    run.ctx.config["apply_instances"] = [GCE]
    with caplog.at_level("WARNING"):
        summary = run.run(["base-image"], apply=False)
    assert summary.ok and any("run scope (dry run, not refused)" in r.message for r in caplog.records)


def test_a_run_with_no_apply_scope_bakes_wherever_the_tree_says(fresh):
    from cs_image_system.base.commands.run_scope import apply_scope_runtimes
    run = fresh(dry_run=False)
    assert apply_scope_runtimes(run.ctx) is None                  # flags off, no --apply-runtime
    run.ctx.config["apply_instances"] = True
    assert apply_scope_runtimes(run.ctx) is None                  # a bool flag: the whole lifecycle
    run.ctx.config["apply_instances"] = ["tofu-gce"]              # a ROOT name maps to its runtime
    assert apply_scope_runtimes(run.ctx) == {GCE}


# ------------------------------------------------------ session lifetimes

def _aws_dir(tmp_path: Path, profile: str, start_url: str, expires: datetime | None) -> Path:
    d = tmp_path / "aws"
    (d / "sso" / "cache").mkdir(parents=True)
    (d / "config").write_text(f"[profile {profile}]\nregion = us-east-2\nsso_start_url = {start_url}\n"
                              "sso_region = us-east-1\nsso_account_id = 1\nsso_role_name = r\n\n"
                              "[profile static]\nregion = us-east-2\n")
    if expires is not None:
        key = hashlib.sha1(start_url.encode()).hexdigest()
        (d / "sso" / "cache" / f"{key}.json").write_text(json.dumps({
            "startUrl": start_url, "region": "us-east-1", "accessToken": "SECRET-NEVER-PRINTED",
            "expiresAt": expires.strftime("%Y-%m-%dT%H:%M:%SZ")}))
    return d


def test_sso_expiry_is_read_from_the_cache_without_touching_the_token(tmp_path):
    from cs_image_system.base.commands.preflight import aws_sso_expiry
    now = datetime.now(timezone.utc).replace(microsecond=0)
    d = _aws_dir(tmp_path, "noaa", "https://x.awsapps.com/start", now + timedelta(hours=8))
    exp, note = aws_sso_expiry("noaa", d)
    assert exp == now + timedelta(hours=8) and "SECRET" not in note
    assert aws_sso_expiry("static", d) == (None, "profile 'static' is not an SSO profile (no expiry readable)")
    assert aws_sso_expiry("nobody", d)[0] is None
    d2 = _aws_dir(tmp_path / "b", "noaa", "https://y.awsapps.com/start", None)
    assert "aws sso login --profile noaa" in aws_sso_expiry("noaa", d2)[1]


def test_preflight_lines_flag_a_session_shorter_than_the_expected_run(fresh, tmp_path, monkeypatch):
    from cs_image_system.base.commands.preflight import session_lines
    run = fresh()
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("CSIS_AWS_DIR", str(_aws_dir(tmp_path, "noaa", "https://x.awsapps.com/start",
                                                    now + timedelta(minutes=12))))
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "missing-adc.json"))
    lines, blocking = session_lines(run.ctx, now)
    aws_line = next(ln for ln in lines if f"{AWS}" in ln and "(aws, profile noaa)" in ln)
    assert "expires in 12 min -- SHORTER than the expected run (30 min)" in aws_line
    assert blocking == [aws_line]                                # one line per SOURCE, default window 30 min
    assert aws_line.startswith("session: aws-east1, aws-east2-runtime")   # every runtime on that profile
    gcp_line = next(ln for ln in lines if f"{GCE}" in ln and "(gcp, " in ln)
    assert "no Application Default Credentials found" in gcp_line and gcp_line not in blocking
    run.ctx.config["preflight"] = {"expected_run_minutes": 10}   # the operator's own window
    _, blocking = session_lines(run.ctx, now)
    assert blocking == []
    monkeypatch.setenv("CSIS_AWS_DIR", str(_aws_dir(tmp_path / "e", "noaa", "https://x.awsapps.com/start",
                                                    now - timedelta(minutes=1))))
    _, blocking = session_lines(run.ctx, now)
    assert blocking and "EXPIRED" in blocking[0]
    assert not any("SECRET" in ln for ln in lines)


def test_raw_session_lines_need_no_loaded_configuration(tmp_path, monkeypatch):
    """The callback reads sessions from the raw runtime-builders.yml before the
    configuration loads (a load dies on an expired AWS session in the
    networking validation, before any preflight could say so)."""
    from cs_image_system.base.commands.preflight import raw_session_lines
    root = copy_config(tmp_path)
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("CSIS_AWS_DIR", str(_aws_dir(tmp_path, "noaa", "https://x.awsapps.com/start",
                                                    now - timedelta(minutes=5))))
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "missing-adc.json"))
    lines, blocking, expired = raw_session_lines(root, None, now)
    assert any(ln.startswith("session: aws-east1, aws-east2-runtime") and "EXPIRED" in ln for ln in lines)
    assert expired and expired == blocking[:1]
    assert any("(gcp, ADC)" in ln for ln in lines)
    overlay = tmp_path / "pre.yaml"
    overlay.write_text("config:\n  preflight:\n    expected_run_minutes: 100000\n")
    monkeypatch.setenv("CSIS_AWS_DIR", str(_aws_dir(tmp_path / "f", "noaa", "https://x.awsapps.com/start",
                                                    now + timedelta(hours=8))))
    lines, blocking, expired = raw_session_lines(root, [overlay], now)
    assert not expired and blocking and "SHORTER than the expected run (100000 min)" in blocking[0]


# ------------------------------------------------ ledger 70: roots and follow

def test_only_runtime_scopes_the_terraform_roots_too(tmp_path, monkeypatch):
    """A run scoped to one runtime's images generates and plans no OTHER
    runtime's root (the GCE instance root's family lookup 404'd during a
    scoped AWS bake). A list-valued apply flag alone is NOT a scope: the
    §7 decision keeps every root planning and gating under it."""
    from cs_image_system.base.utils import root_in_runtime_scope
    root = copy_config(tmp_path)
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        run.ctx.only_runtime_scope = AWS
        assert root_in_runtime_scope(AWS) and not root_in_runtime_scope(GCE) and root_in_runtime_scope(None)
        summary = run.run(["storage", "instance-image"], apply=True, only=["none"])
        assert summary.ok, summary.error
        roots = {p.relative_to(run.generated).parts[1] for p in run.generated.rglob("*.tf")}
        assert "open-tofu" in roots and "aws-ebs" in roots
        assert not any(r.startswith(("tofu-gce", "gcp-")) for r in roots)
        script = (run.generated / "instance-image" / "run-instance-image.sh").read_text()
        assert "tofu-gce" not in script and "open-tofu/instance-generation" in script
        run.ctx.only_runtime_scope = None
        run.ctx.config["apply_instances"] = [GCE]                   # §7: a flag list scopes applies only
        summary = run.run(["instance-image"], apply=True, only=["none"])
        assert summary.ok, summary.error
        script = (run.generated / "instance-image" / "run-instance-image.sh").read_text()
        assert "tofu-gce/instance-generation" in script and "open-tofu/instance-generation" in script
    finally:
        run.restore_cwd()


def test_follow_child_bakes_when_its_parent_bakes_in_the_same_run(fresh):
    """The dask child under parent_policy: follow read "current" while its
    parent was being re-baked in the same run (the new head is recorded only
    after the bake, so the pin/head comparison saw nothing). A parent that
    bakes this run is a move: the child bakes from the series and the pin
    follows at record time."""
    from cs_image_system.base.lineage import effective_parent_build, find_image
    run = fresh()
    ms = run.ctx.meta_state
    common = {"parent": "vendor", "chain": [], "mods": [], "local_mods": False, "update": None,
              "tests": {"assertions": 0, "in_bake": True},
              "capabilities": {"identity_types": ["okta"], "storage_types": ["ebs"]}, "runtime": AWS}
    ms.add_build({**common, "build_id": "ami-base-old", "series": "basic-rh-10", "name": "b",
                  "run": "2026_09_01t00_00_00_000000", "input_fingerprint": "0" * 64})     # stale: will re-bake
    ms.add_build({**common, "build_id": "ami-dask-old", "series": "imgfile-basic-dask", "name": "d",
                  "parent": "ami-base-old", "run": "2026_09_01t00_00_00_000000", "input_fingerprint": "1" * 64})
    ms.bind_image("imgfile-basic-dask", "ami-base-old", "r0", AWS)
    summary = run.run(["base-image", "instance-image"], apply=False, only=[f"basic-rh-10@{AWS}",
                                                                          f"imgfile-basic-dask@{AWS}"])
    assert summary.ok, summary.error
    plan = summary.bake_plan
    assert plan[f"basic-rh-10@{AWS}"].startswith("bake: inputs changed")
    assert plan[f"imgfile-basic-dask@{AWS}"] == "bake: parent ami-base-old re-bakes this run (parent_policy: follow)"
    dask = find_image(run.ctx, "imgfile-basic-dask", AWS)
    # the parent REFERENCE (and so the fingerprint) stays the pin: a bake decision never moves a fingerprint
    assert effective_parent_build(run.ctx, dask, AWS) == ("ami-base-old", None)
