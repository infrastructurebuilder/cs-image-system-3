# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Loading once, without the cloud.

A load asks no cloud about networking: the runtime models' ``finalize()``
is pure, and what an account answers a runtime's networking declaration
with is discovered ONLINE by a real run and by ``validate --online`` (the
builder's ``network_facts`` hook), recorded in
``meta-state/runtime-facts.yaml``, and adopted OFFLINE by every load (the
builder's ``adopt_network_facts`` hook). ``validate``, a dry run and
``preflight`` read the record; what the record does not cover is a
validation error that names ``validate --online``. A subnet outside the
VPC is the online check's refusal, in the plugin's words.

History: stage 127 item 1, stage 63 dead-code item 2.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from harness import (
    FIXED_CHECKED_AT,
    FIXTURE_CONFIG,
    V2Run,
    copy_config,
    load_context,
    record_network_facts,
    stub_environment,
)

FACTS = Path("meta-state") / "runtime-facts.yaml"


def _forbid_discovery(monkeypatch) -> list[str]:
    """Every cloud discovery call raises; the journal says which one was made."""
    from cs_image_system.aws_runtime import aws_utils
    from cs_image_system.gcloud_runtime import gcp_utils
    calls: list[str] = []

    def aws(session_config):
        calls.append("aws")
        raise AssertionError("a load reached EC2 (get_vpc_map_and_default_vpc_id)")

    def gcp(session_config, clients=None):
        calls.append("gcp")
        raise AssertionError("a load reached Compute (get_network_map_and_default_network)")
    monkeypatch.setattr(aws_utils, "get_vpc_map_and_default_vpc_id", aws)
    monkeypatch.setattr(gcp_utils, "get_network_map_and_default_network", gcp)
    return calls


def _errors(ctx) -> list[str]:
    from cs_image_system.base.commands.run_lifecycles import validate_only
    return validate_only(ctx)


def _set_network(root: Path, runtime: str, network: str) -> None:
    rb = root / "cfg" / "runtime-builders.yml"
    d = yaml.safe_load(rb.read_text())
    entry = next(r for r in d["runtime_builders"] if r["name"] == runtime)
    entry["networking"]["network"] = network
    rb.write_text(yaml.safe_dump(d, sort_keys=False))


# ------------------------------------------------------ (a) a load asks nothing

def test_loading_the_fixture_never_reaches_a_cloud(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    calls = _forbid_discovery(monkeypatch)
    root = copy_config(tmp_path)
    ctx = load_context(root)
    assert calls == []
    # the record the harness wrote was adopted: the `default` networks are the recorded ones
    assert ctx.runtime_builders["west1"].model.networking.network == "default"
    assert ctx.runtime_builders["gcloud-east1"].model.networking.network == "default"
    assert ctx.runtime_builders["aws-east2-runtime"].model.networking.network == "vpc-0c78d0d63b7a100df"
    assert ctx.network_facts_problems == []
    assert _errors(ctx) == []
    # the account's inventory was never fetched
    assert ctx.runtime_builders["aws-east2-runtime"].model.vpc_map is None
    # a dry run asks nothing either
    run = V2Run(tmp_path / "dry", monkeypatch)
    try:
        summary = run.run("all")
        assert summary.ok, summary.error
        assert calls == []
        assert yaml.safe_load((run.config_root / FACTS).read_text())["runtimes"]["west1"]["checked_at"] == FIXED_CHECKED_AT
    finally:
        run.restore_cwd()


def test_the_frozen_fixture_loads_with_no_record_and_writes_none(monkeypatch):
    """`preflight` loads the frozen fixture itself; a load never writes the record."""
    stub_environment(monkeypatch)
    _forbid_discovery(monkeypatch)
    ctx = load_context(FIXTURE_CONFIG)
    assert not (FIXTURE_CONFIG / "meta-state").exists()
    assert any("records nothing" in p for p in ctx.network_facts_problems)


# ------------------------------- (b) a `default` network with no record fails validate

def test_validate_names_the_online_flag_for_a_default_network_nothing_recorded(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    _forbid_discovery(monkeypatch)
    root = copy_config(tmp_path)
    (root / FACTS).unlink()
    ctx = load_context(root)
    errors = _errors(ctx)
    west = [e for e in errors if e.startswith("runtime 'west1'")]
    assert west, errors
    assert any("`default`" in e and "validate --online" in e for e in west), west
    # a runtime that declares a concrete network is unchecked too: its subnets were never checked
    assert any(e.startswith("runtime 'aws-east2-runtime'") and "subnet-09f79018af845358a" in e
               and "validate --online" in e for e in errors), errors
    # the model itself still says `default`: nothing resolved it
    assert ctx.runtime_builders["west1"].model.networking.network == "default"


# ------------------------------------- (c) discover writes the record; a later load adopts it

def test_discover_writes_the_record_and_the_next_offline_load_adopts_it(tmp_path: Path, monkeypatch):
    from cs_image_system.base import network_facts
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)
    (root / FACTS).unlink()
    ctx = load_context(root)
    assert _errors(ctx)
    recorded = network_facts.discover(ctx)                   # ONLINE (the harness's stubs answer)
    assert set(recorded) == {"aws-east2-runtime", "gcloud-east1", "aws-east1", "west1"}
    assert recorded["west1"]["network"] == "default" and recorded["west1"]["security_groups"] == []
    assert recorded["aws-east2-runtime"]["security_groups"] == ["sg-03015ec107ae5f81a"]
    assert recorded["gcloud-east1"]["subnets"] == ["projects/csis-sandbox/regions/us-east1/subnetworks/default"]
    assert "security_groups" not in recorded["gcloud-east1"]
    on_disk = yaml.safe_load((root / FACTS).read_text())
    assert on_disk == {"runtimes": recorded}
    # small and public-safe: the ids the tree declares, never the account's inventory
    assert set(recorded["aws-east2-runtime"]) == {"network", "subnets", "security_groups", "checked_at"}
    assert network_facts.adopt(ctx) == [] and ctx.network_facts_problems == []
    # the next load asks nothing and adopts what was recorded
    _forbid_discovery(monkeypatch)
    again = load_context(root)
    assert again.network_facts_problems == [] and _errors(again) == []
    assert again.runtime_builders["west1"].model.networking.network == "default"


def test_validate_online_discovers_then_validates(tmp_path: Path, monkeypatch):
    from cs_image_system.base.commands.run_lifecycles import validate_only
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)
    (root / FACTS).unlink()
    ctx = load_context(root)
    assert validate_only(ctx)                                  # offline: the record is missing
    assert validate_only(ctx, online=True) == []               # online: discovered, recorded, adopted
    assert (root / FACTS).is_file()


def test_a_failing_online_check_is_one_classified_line_with_its_exit_code(tmp_path: Path, monkeypatch):
    """The plugin's own refusal (a subnet outside the VPC) keeps its words; a
    lapsed session is the one line a load-time failure used to get."""
    from cs_image_system.aws_runtime import aws_utils
    from cs_image_system.base import network_facts
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)
    ctx = load_context(root)

    class ProfileNotFound(Exception):          # botocore's class, matched by name
        pass

    def lapsed(session_config):
        raise ProfileNotFound("The config profile (noaa) could not be found")
    monkeypatch.setattr(aws_utils, "get_vpc_map_and_default_vpc_id", lapsed)
    with pytest.raises(network_facts.NetworkFactsError) as exc:
        network_facts.discover(ctx)
    assert exc.value.runtime == "aws-east1" and isinstance(exc.value.__cause__, ProfileNotFound)
    assert exc.value.lines[0].startswith("runtime 'aws-east1'")
    # the CLI prints those lines and exits with that code
    from typer.testing import CliRunner

    from cs_image_system.system.cli import app
    result = CliRunner().invoke(app, ["--root-dir", str(root), "validate", "--online"])
    assert result.exit_code == 2, result.output
    assert "ProfileNotFound" in result.output and "Traceback" not in result.output


# ------------------------------------------- (d) a real run refreshes the record

def test_a_real_run_discovers_and_refreshes_checked_at(tmp_path: Path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch, dry_run=False)
    try:
        before = yaml.safe_load((run.config_root / FACTS).read_text())
        assert before["runtimes"]["west1"]["checked_at"] == FIXED_CHECKED_AT
        summary = run.run("base-image", apply=False)                 # a REAL run: discovery happens before validation
        assert summary.ok, summary.error
        after = yaml.safe_load((run.config_root / FACTS).read_text())
        assert after["runtimes"]["west1"]["checked_at"] != FIXED_CHECKED_AT
        assert after["runtimes"]["west1"]["network"] == "default"
        assert after["runtimes"]["aws-east2-runtime"]["subnets"] == before["runtimes"]["aws-east2-runtime"]["subnets"]
        assert run.ctx.network_facts_problems == []
    finally:
        run.restore_cwd()


# ----------------------------------------------- (e) stale facts are a validation error

def test_stale_facts_are_a_validation_error(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    _forbid_discovery(monkeypatch)
    root = copy_config(tmp_path)
    data = yaml.safe_load((root / FACTS).read_text())
    data["runtimes"]["aws-east2-runtime"]["subnets"].remove("subnet-00075cfbfcbc8f2cf")   # declared, never checked
    data["runtimes"]["aws-east2-runtime"]["security_groups"] = []                           # the declared SG neither
    (root / FACTS).write_text(yaml.safe_dump(data))
    errors = _errors(load_context(root))
    stale = [e for e in errors if e.startswith("runtime 'aws-east2-runtime'")]
    assert len(stale) == 1, errors
    assert "stale" in stale[0] and "subnet-00075cfbfcbc8f2cf" in stale[0] and "sg-03015ec107ae5f81a" in stale[0]
    assert "validate --online" in stale[0]
    assert not [e for e in errors if e.startswith("runtime 'aws-east1'")]       # covered: adopts silently


def test_a_network_that_changed_since_the_record_is_stale_too(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    _forbid_discovery(monkeypatch)
    root = copy_config(tmp_path)
    _set_network(root, "aws-east1", "vpc-0c78d0d63b7a100df")          # the record checked vpc-0381e9f82c9ae68e7
    errors = _errors(load_context(root))
    assert any(e.startswith("runtime 'aws-east1'") and "stale" in e and "network vpc-0c78d0d63b7a100df" in e
               and "vpc-0381e9f82c9ae68e7" in e for e in errors), errors


def test_the_record_is_derived_from_the_tree_and_the_hooks_are_optional(tmp_path: Path, monkeypatch):
    """The base builder's hooks answer nothing: a runtime without them (the
    harness's record covers only aws and gcloud) is neither asked nor judged."""
    from cs_image_system.base.basic.builder_base_runtime import RuntimeBuilderBase
    from cs_image_system.base.network_facts import coverage_problems, facts_of
    assert RuntimeBuilderBase.network_facts(object()) == {}         # type: ignore[arg-type]
    assert RuntimeBuilderBase.adopt_network_facts(object(), {}) == []   # type: ignore[arg-type]
    facts = facts_of("vpc-1", ["subnet-a"], ["sg-1"])
    assert facts["network"] == "vpc-1" and facts["subnets"] == ["subnet-a"] and facts["security_groups"] == ["sg-1"]
    assert "+00:00" in facts["checked_at"]
    assert "security_groups" not in facts_of("default", ["s"])
    assert coverage_problems("r", facts, declared_network="vpc-1", subnets=["subnet-a"], security_groups=["sg-1"]) == []
    assert coverage_problems("r", {}, declared_network="default", subnets=["subnet-a"]) == []     # adopt() says it
    assert "records nothing" in coverage_problems("r", {}, declared_network="vpc-1", subnets=["subnet-a"])[0]
    root = copy_config(tmp_path)
    written = yaml.safe_load(record_network_facts(root).read_text())["runtimes"]
    assert set(written) == {"aws-east2-runtime", "gcloud-east1", "aws-east1", "west1"}


# ------------------------------------------------------------ (f) preflight over a loaded tree

def _preflight(monkeypatch, root: Path, *args: str, **env: str):
    from typer.testing import CliRunner

    from cs_image_system.system.cli import app
    for var in ("AWS_PROFILE", "AWS_ACCESS_KEY_ID"):
        monkeypatch.delenv(var, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return CliRunner().invoke(app, ["--root-dir", str(root), "preflight", *args])


def test_preflight_loads_the_configuration_offline_and_exits_as_documented(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    calls = _forbid_discovery(monkeypatch)
    # the fixture's container runtime is no cloud session: its daemon probe answers here
    from cs_image_system.docker_runtime import docker_runtime_builders as drb
    monkeypatch.setattr(drb, "probe_daemon", lambda binary, env, timeout=20: (True, "answers: stub"))
    root = copy_config(tmp_path)
    (root / FACTS).unlink()                      # preflight judges sessions, not the record
    # conftest: an empty AWS dir, no ADC -- every session absent: exit 2
    result = _preflight(monkeypatch, root)
    assert result.exit_code == 2, result.output
    assert "aws-east2-runtime" in result.output and "gcloud-east1" in result.output
    assert "EXPIRED" in result.output and calls == []
    # static keys and an ADC: present, NOT JUDGED, exit 0, never "every session present"
    adc = tmp_path / "adc.json"
    adc.write_text(json.dumps({"type": "authorized_user"}))
    result = _preflight(monkeypatch, root, AWS_ACCESS_KEY_ID="AKIA-test", GOOGLE_APPLICATION_CREDENTIALS=str(adc))
    assert result.exit_code == 0, result.output
    assert "NOT JUDGED" in result.output and "AKIA-test" not in result.output
    # a credential set but EMPTY: exit 2, by name
    result = _preflight(monkeypatch, root, AWS_ACCESS_KEY_ID="AKIA-test", GOOGLE_APPLICATION_CREDENTIALS=str(adc),
                        TF_VAR_NOS_KEY="")
    assert result.exit_code == 2 and "TF_VAR_NOS_KEY" in result.output and "EMPTY" in result.output, result.output
    assert calls == [] and not (root / FACTS).exists()
    # `preflight` loads: a tree that cannot load is the loader's one line, not a session verdict
    result = _preflight(monkeypatch, tmp_path / "nowhere")
    assert result.exit_code != 0 and "preflight:" not in result.output


def test_a_subnet_outside_the_vpc_is_refused(tmp_path: Path, monkeypatch):
    """The check is the runtime's ONLINE network check (run by a
    real run and `validate --online` through `network_facts.discover`, never
    by a load), and the refusal keeps its words."""
    from cs_image_system.aws_runtime import aws_utils
    from cs_image_system.base import network_facts
    stub_environment(monkeypatch)
    real = aws_utils.get_vpc_map_and_default_vpc_id

    def with_subnets(session_config):
        vpcs, default, sgs = real(session_config)
        return ({v: {"subnets": [{"subnet_id": "subnet-somewhere-else"}]} for v in vpcs}, default, sgs)
    monkeypatch.setattr(aws_utils, "get_vpc_map_and_default_vpc_id", with_subnets)
    ctx = load_context(copy_config(tmp_path))          # the load asks nothing
    with pytest.raises(network_facts.NetworkFactsError) as exc:
        network_facts.discover(ctx)
    assert "VPC" in str(exc.value) and "aws-east1" in str(exc.value), str(exc.value)
    assert isinstance(exc.value.__cause__, ValueError)
