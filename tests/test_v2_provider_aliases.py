# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 58: an instance answers to its provider's names too.

The instance id and the address already resolve natively (settled live,
2026-09-21); the provider's own hostname does not, because the boot script
overwrites it. These tests hold the rules for giving it back: only after
launch, only to a running machine, never on a collision, never on silence,
and idempotently -- the same names twice touch nothing.

Providers are faked at the runtime and group-builder hook seams.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.v2_support import V2Run

from cs_image_system.base import power_state as ps
from cs_image_system.base import provider_aliases as pa
from cs_image_system.base import state_query as sq
from cs_image_system.base.lifecycles import Lifecycle

EC2 = {"instance_id": "i-0169f82844f4cc08d",
       "provider_hostname": "ip-10-26-34-156.us-east-2.compute.internal"}
GCE = {"instance_id": "1234567890", "provider_hostname": "gce-test.c.csis-sandbox.internal"}


# ------------------------------------------------------------ pure rules

def test_the_label_is_the_first_part_of_the_provider_hostname():
    assert pa.provider_hostname_label(EC2["provider_hostname"]) == "ip-10-26-34-156"
    assert pa.provider_hostname_label("") is None and pa.provider_hostname_label(None) is None


def test_ec2_gives_back_the_ip_name_and_gce_has_nothing_to_give():
    assert pa.wanted_aliases(EC2, "coops-model") == ["ip-10-26-34-156"]
    assert pa.wanted_aliases(GCE, "gce-test") == []      # the label IS the name
    assert pa.wanted_aliases(None, "coops-model") == []
    assert pa.wanted_aliases({"provider_hostname": "bad_name.x"}, "n") == []   # not a label


def test_a_suffixed_canonical_name_gives_the_bare_name_back_too():
    """Stage 55 step 4: coops-model-003 is the canonical name; coops-model is
    what a person types, so it rides along as an alias."""
    assert pa.wanted_aliases(EC2, "coops-model-003", "coops-model") == ["coops-model", "ip-10-26-34-156"]
    assert pa.wanted_aliases(None, "coops-model-003", "coops-model") == ["coops-model"]
    assert pa.wanted_aliases(None, "coops-model", "coops-model") == []       # grandfathered: no suffix


def test_every_name_a_record_answers_to_is_a_claim():
    servers = [{"id": "A", "hostname": "coops-model", "canonical_name": "coops-model-003",
                "alt_names": ["ip-10-26-35-236"]}]
    claims = pa.claimed_names(servers, {"gce-test"})
    assert claims == {"gce-test": "declared", "coops-model": "A", "coops-model-003": "A",
                      "ip-10-26-35-236": "A"}


def test_own_record_is_found_by_the_provider_id_not_the_name():
    """Three records bore one hostname on 2026-09-21; only the instance id
    told the live one from the stale ones."""
    servers = [{"id": "stale", "hostname": "coops-model", "instance_id": "i-dead"},
               {"id": "live", "hostname": "coops-model", "instance_id": EC2["instance_id"]}]
    own = pa.own_record(servers, EC2["instance_id"])
    assert own is not None and own["id"] == "live"
    assert pa.own_record(servers, "") is None


def test_the_script_rewrites_the_last_block_and_restarts_only_on_change():
    s = pa.alt_names_script(["ip-10-26-34-156"])
    assert "AltNames:" in s and "  - ip-10-26-34-156" in s
    assert "sed -i '/^AltNames:/,$d'" in s          # replace from the heading to EOF
    assert "ALTNAMES_UNCHANGED; exit 0" in s          # idempotent path first
    assert "systemctl restart sftd" in s and s.index("UNCHANGED") < s.index("restart sftd")
    assert "tee -a" in s and "| sudo tee " not in s.replace("tee -a", "")   # append, never truncate
    assert 'want=""' in pa.alt_names_script([])       # no aliases: the block is removed
    with pytest.raises(ValueError, match="not a hostname label"):
        pa.alt_names_script(["ip 10"])


# ------------------------------------------------------------- the hook

@pytest.fixture
def world(tmp_path: Path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        yield run
    finally:
        run.restore_cwd()


class Fakes:
    """Runtime + registry seams for one instance named `test`."""

    def __init__(self, monkeypatch, *, identity=EC2, state=ps.RUNNING, servers=None):
        from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
        from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
        self.scripts: list[tuple[str, str]] = []
        self.servers = servers
        monkeypatch.setattr(AwsCloudBuilder, "can_query_instance_identity", lambda s: True)
        monkeypatch.setattr(AwsCloudBuilder, "query_instance_identity",
                            lambda s, n: dict(identity) if identity and n == "test" else None)
        monkeypatch.setattr(AwsCloudBuilder, "can_query_instance_power_state", lambda s: True)
        monkeypatch.setattr(AwsCloudBuilder, "query_instance_power_state", lambda s, n: state)
        monkeypatch.setattr(AwsCloudBuilder, "run_session_command",
                            lambda s, n, script, timeout=300: self.scripts.append((n, script)) or (0, "ALTNAMES_CHANGED"))
        monkeypatch.setattr(OktaTfGroupBuilder, "can_query_servers", lambda s: True)
        monkeypatch.setattr(OktaTfGroupBuilder, "registered_servers", lambda s, g: self.servers)


def _launched(ctx, name="test") -> None:
    ms = ctx.meta_state
    rec: dict[str, Any] = dict(ms.launch_params().get(name) or {"hostname": name, "group": "coops"})
    rec["launched"] = True
    ms.record_launch_params(name, rec)
    ctx.config["apply_instances"] = True


OWN = {"id": "live", "hostname": "test", "instance_id": EC2["instance_id"], "alt_names": []}


def test_a_launched_running_instance_gets_its_ip_name_back(world, monkeypatch):
    f = Fakes(monkeypatch, servers=[OWN])
    _launched(world.ctx)
    pa.register_provider_aliases(world.ctx, Lifecycle.INSTANCE_IMAGE)
    assert [n for n, _ in f.scripts] == ["test"]
    assert "  - ip-10-26-34-156" in f.scripts[0][1]


def test_nothing_happens_for_an_unlaunched_instance_or_without_applies(world, monkeypatch):
    f = Fakes(monkeypatch, servers=[OWN])
    world.ctx.config["apply_instances"] = True
    pa.register_provider_aliases(world.ctx, Lifecycle.INSTANCE_IMAGE)   # not launched
    assert f.scripts == []
    _launched(world.ctx)
    world.ctx.config["apply_instances"] = False
    pa.register_provider_aliases(world.ctx, Lifecycle.INSTANCE_IMAGE)   # dry run
    pa.register_provider_aliases(world.ctx, Lifecycle.BASE_IMAGE)       # wrong lifecycle
    assert f.scripts == []


def test_a_machine_that_is_off_is_left_off(world, monkeypatch, caplog):
    """Stage 57: an alias is not worth starting a machine for."""
    f = Fakes(monkeypatch, state=ps.STOPPED, servers=[OWN])
    _launched(world.ctx)
    with caplog.at_level("INFO"):
        pa.register_provider_aliases(world.ctx, Lifecycle.INSTANCE_IMAGE)
    assert f.scripts == []
    assert any("waits for a run that finds it running" in r.message for r in caplog.records)


def test_a_claimed_alias_is_skipped_and_the_claimant_named(world, monkeypatch, caplog):
    stale = {"id": "stale", "hostname": "ip-10-26-34-156", "instance_id": "i-dead", "alt_names": []}
    f = Fakes(monkeypatch, servers=[OWN, stale])
    _launched(world.ctx)
    with caplog.at_level("WARNING"):
        pa.register_provider_aliases(world.ctx, Lifecycle.INSTANCE_IMAGE)
    assert f.scripts == [] or "  - ip-10-26-34-156" not in f.scripts[0][1]
    assert any("SKIPPED" in r.message and "stale" in r.message for r in caplog.records)


def test_a_declared_instance_name_is_a_claim_too(world, monkeypatch, caplog):
    """If someone declares an instance literally named ip-10-26-34-156."""
    f = Fakes(monkeypatch, servers=[OWN])
    _launched(world.ctx)
    monkeypatch.setattr(pa, "canonical_hostname",
                        lambda ctx, i: "ip-10-26-34-156" if i.get_name() == "test2" else i.get_name())
    with caplog.at_level("WARNING"):
        pa.register_provider_aliases(world.ctx, Lifecycle.INSTANCE_IMAGE)
    assert f.scripts == []
    assert any("claimed by declared" in r.message for r in caplog.records)


def test_silence_skips_every_alias(world, monkeypatch, caplog):
    f = Fakes(monkeypatch, servers=None)
    _launched(world.ctx)
    with caplog.at_level("WARNING"):
        pa.register_provider_aliases(world.ctx, Lifecycle.INSTANCE_IMAGE)
    assert f.scripts == []
    assert any("silence is not a free name" in r.message for r in caplog.records)


def test_reality_that_already_agrees_sends_no_command(world, monkeypatch):
    own = dict(OWN, alt_names=["ip-10-26-34-156"])
    f = Fakes(monkeypatch, servers=[own])
    _launched(world.ctx)
    pa.register_provider_aliases(world.ctx, Lifecycle.INSTANCE_IMAGE)
    assert f.scripts == []


def test_a_stale_record_bearing_our_own_name_does_not_block_our_alias(world, monkeypatch):
    """A stale `test` record (the stage-55 shape) claims `test`, not the ip
    name; our own record is told apart by instance id and the alias goes on."""
    stale = {"id": "stale", "hostname": "test", "instance_id": "i-dead", "alt_names": []}
    f = Fakes(monkeypatch, servers=[stale, OWN])
    _launched(world.ctx)
    pa.register_provider_aliases(world.ctx, Lifecycle.INSTANCE_IMAGE)
    assert len(f.scripts) == 1 and "  - ip-10-26-34-156" in f.scripts[0][1]


# ------------------------------------------------------- the state query

def test_the_report_says_what_a_machine_answers_to(world, monkeypatch):
    Fakes(monkeypatch, servers=[OWN])
    _launched(world.ctx)
    report = sq.query_state(world.ctx)
    inst = report.reality["instances"]["test"]
    assert inst["instance_id"] == EC2["instance_id"] and inst["registered_as"] == "test"
    assert inst["alt_names"] == []
    assert any("not yet to ['ip-10-26-34-156']" in n for n in report.notes)


def test_the_report_is_quiet_once_the_alias_is_there_or_the_machine_is_off(world, monkeypatch):
    Fakes(monkeypatch, servers=[dict(OWN, alt_names=["ip-10-26-34-156"])])
    _launched(world.ctx)
    report = sq.query_state(world.ctx)
    assert not any("not yet to" in n for n in report.notes)
    Fakes(monkeypatch, state=ps.STOPPED, servers=[OWN])
    report = sq.query_state(world.ctx)
    assert not any("not yet to" in n for n in report.notes)
