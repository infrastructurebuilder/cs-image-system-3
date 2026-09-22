# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 57: the power state belongs to the operator.

An instance is created running; after that the system never forces it back.
The tests here hold the three rules that make that true -- "cannot answer" is
not "stopped", off is not drift, and a machine started for a bounded task goes
back off even when the task explodes.

The clouds are faked at the plugin seam: what is under test is the vocabulary
and the rules, not boto3 or google.cloud.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.v2_support import V2Run

from cs_image_system.base import power_state as ps
from cs_image_system.base import state_query as sq


# --------------------------------------------------------- the vocabulary

def test_silence_is_not_a_state():
    """The rule the whole stage rests on: a runtime that cannot answer
    returns None, and None is never read as 'switched off'."""
    assert ps.is_off(None) is False
    assert ps.is_on(None) is False
    assert ps.exists(None) is False
    assert "unavailable" in ps.describe(None)


def test_off_states_are_off_and_transitional_states_are_not():
    assert ps.is_off(ps.STOPPED) and ps.is_off(ps.SUSPENDED)
    assert not ps.is_off(ps.STOPPING)      # on its way down is not down yet
    assert not ps.is_on(ps.STARTING)       # coming up is not up
    assert ps.is_on(ps.RUNNING)
    assert not ps.exists(ps.ABSENT)


def test_describe_names_a_stopped_machine_as_not_drift():
    """The report has to say this plainly, because the operator chose it."""
    assert "not drift" in ps.describe(ps.STOPPED)
    assert "not drift" in ps.describe(ps.SUSPENDED)


# ------------------------------------------------------- provider mappings

@pytest.mark.parametrize(("raw", "expected"), [
    ("running", ps.RUNNING),
    ("stopped", ps.STOPPED),
    ("pending", ps.STARTING),
    ("stopping", ps.STOPPING),
    ("shutting-down", ps.STOPPING),
    ("terminated", ps.ABSENT),
])
def test_ec2_states_map_onto_our_words(raw, expected):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    assert AwsCloudBuilder._EC2_POWER[raw] == expected


@pytest.mark.parametrize(("raw", "expected"), [
    ("RUNNING", ps.RUNNING),
    ("PROVISIONING", ps.STARTING),
    ("STAGING", ps.STARTING),
    ("SUSPENDED", ps.SUSPENDED),
    ("TERMINATED", ps.STOPPED),
])
def test_gce_states_map_onto_our_words(raw, expected):
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    assert GCPCloudBuilder._GCE_POWER[raw] == expected


def test_gce_terminated_means_stopped_not_gone():
    """The trap the shared vocabulary exists to defuse: on GCE TERMINATED is
    a machine that can be started again, and on EC2 the same word is a
    machine that no longer exists. A caller reading raw provider spellings
    would get this exactly backwards."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    assert GCPCloudBuilder._GCE_POWER["TERMINATED"] == ps.STOPPED
    assert AwsCloudBuilder._EC2_POWER["terminated"] == ps.ABSENT
    assert ps.exists(GCPCloudBuilder._GCE_POWER["TERMINATED"])
    assert not ps.exists(AwsCloudBuilder._EC2_POWER["terminated"])


# ------------------------------------------------------- the bounded start

class FakeRuntime:
    """A runtime builder reduced to the hooks stage 57 added."""

    def __init__(self, state, *, can_query=True, can_set=True, reachable=True):
        self.state = state
        self._can_query, self._can_set, self._reachable = can_query, can_set, reachable
        self.started, self.stopped = 0, 0

    def get_name(self) -> str:
        return "fake-runtime"

    def can_query_instance_power_state(self) -> bool:
        return self._can_query

    def query_instance_power_state(self, name):
        return self.state

    def can_set_instance_power_state(self) -> bool:
        return self._can_set

    def start_instance(self, name, timeout=300):
        self.started += 1
        self.state = ps.RUNNING
        return True

    def stop_instance(self, name, timeout=300):
        self.stopped += 1
        self.state = ps.STOPPED
        return True

    def run_session_command(self, name, script, timeout=300):
        return (0, "") if self._reachable else (1, "no")


def test_a_running_machine_is_left_alone():
    rtb = FakeRuntime(ps.RUNNING)
    with ps.running_for_task(rtb, "m", why="a test") as available:
        assert available
    assert (rtb.started, rtb.stopped) == (0, 0)


def test_a_runtime_that_cannot_answer_changes_nothing():
    """No knowledge means behave exactly as before the stage: never start a
    machine on the strength of a query that returned nothing."""
    rtb = FakeRuntime(None, can_query=False)
    with ps.running_for_task(rtb, "m", why="a test") as available:
        assert available
    assert (rtb.started, rtb.stopped) == (0, 0)


def test_a_stopped_machine_that_cannot_be_started_is_a_skip():
    rtb = FakeRuntime(ps.STOPPED, can_set=False)
    with ps.running_for_task(rtb, "m", why="a test") as available:
        assert available is False
    assert (rtb.started, rtb.stopped) == (0, 0)


def test_a_stopped_machine_is_started_for_the_task_and_put_back():
    rtb = FakeRuntime(ps.STOPPED)
    with ps.running_for_task(rtb, "m", why="a test") as available:
        assert available
        assert rtb.started == 1 and rtb.stopped == 0     # still up during the work
    assert rtb.stopped == 1
    assert rtb.state == ps.STOPPED


def test_the_restore_survives_the_task_failing():
    """The one that matters: one bad run must not cost the operator the
    budget they were conserving by switching the machine off."""
    rtb = FakeRuntime(ps.STOPPED)
    with pytest.raises(RuntimeError, match="the work exploded"):
        with ps.running_for_task(rtb, "m", why="a test"):
            raise RuntimeError("the work exploded")
    assert rtb.started == 1 and rtb.stopped == 1
    assert rtb.state == ps.STOPPED


def test_provider_running_is_not_reachable():
    """The provider flipping to `running` is not sshd answering, so a machine
    that never becomes reachable is a skip -- and is still put back."""
    rtb = FakeRuntime(ps.STOPPED, reachable=False)
    with ps.running_for_task(rtb, "m", why="a test", reachable_timeout=0) as available:
        assert available is False
    assert rtb.started == 1 and rtb.stopped == 1


# ----------------------------------------------------- off is not drift

@pytest.fixture
def world(tmp_path: Path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        yield run
    finally:
        run.restore_cwd()


def _aws_runtime(ctx) -> str:
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    return sorted(n for n, b in ctx.runtime_builders.items() if isinstance(b, AwsCloudBuilder))[0]


def test_a_stopped_instance_is_a_note_not_unavailable(world, monkeypatch):
    """Before stage 57 the boot-image probe answered None for a stopped
    machine exactly as it did for an unreachable cloud, so the report said
    'the provider could not answer' about a decision the operator had made
    deliberately."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    ctx = world.ctx
    rt = _aws_runtime(ctx)
    ctx.meta_state.add_build({"build_id": "ami-x", "series": "imgfile-coops-model", "runtime": rt,
                              "name": "n", "parent": "external", "input_fingerprint": "f", "run": "r",
                              "capabilities": {}, "mods": [], "chain": []})
    ctx.meta_state.bind_instance("test", "ami-x", "run-x")
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_boot_image", lambda self, n: None)
    monkeypatch.setattr(AwsCloudBuilder, "can_query_instance_power_state", lambda self: True)
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_power_state", lambda self, n: ps.STOPPED)

    report = sq.query_state(ctx)
    assert not [d for d in report.drift if d.kind == "instance" and d.name == "test"]
    assert not [u for u in report.unavailable if "instances/test" in u]
    note = [n for n in report.notes if "instances/test" in n]
    assert note and "STOPPED" in note[0]
    assert "still stand" in note[0]
    assert "notes" in report.as_dict()
    assert "note:" in report.render()


def test_an_unreachable_cloud_is_still_unavailable(world, monkeypatch):
    """The other half of the same rule: silence must not be dressed up as a
    deliberate power state."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    ctx = world.ctx
    rt = _aws_runtime(ctx)
    ctx.meta_state.add_build({"build_id": "ami-y", "series": "imgfile-coops-model", "runtime": rt,
                              "name": "n", "parent": "external", "input_fingerprint": "f", "run": "r",
                              "capabilities": {}, "mods": [], "chain": []})
    ctx.meta_state.bind_instance("test", "ami-y", "run-y")
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_boot_image", lambda self, n: None)
    monkeypatch.setattr(AwsCloudBuilder, "can_query_instance_power_state", lambda self: True)
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_power_state", lambda self, n: None)

    report = sq.query_state(ctx)
    assert [u for u in report.unavailable if "instances/test" in u]
    assert not [n for n in report.notes if "instances/test" in n]


def test_a_pending_replacement_is_a_note_not_drift_in_the_strict_query(world, monkeypatch):
    """`upgrade instance` moves the pin and leaves the marker, so the booted
    image is behind the pin BY DESIGN until the next applies-on run replaces
    the machine. The strict query used to call that `changed` drift and so
    refused the very launch that finishes the procedure (cloud-launch's
    preflight, live 2026-09-22). Without the marker it is drift again."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    ctx = world.ctx
    ms = ctx.meta_state
    rt = _aws_runtime(ctx)
    for b in ("ami-old", "ami-new"):
        ms.add_build({"build_id": b, "series": "imgfile-coops-model", "runtime": rt, "name": b,
                      "parent": "external", "input_fingerprint": "f", "run": "r",
                      "capabilities": {}, "mods": [], "chain": []})
    ms.bind_instance("test", "ami-old", "run-x")
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_boot_image", lambda self, n: "ami-old")
    monkeypatch.setattr(AwsCloudBuilder, "can_query_instance_power_state", lambda self: True)
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_power_state", lambda self, n: ps.RUNNING)
    assert not [d for d in sq.query_state(ctx).drift if d.kind == "instance" and d.name == "test"]

    ms.move_pin("instance", "test", "ami-new", "run-y")          # what `upgrade instance` does
    assert "test" in ms.pending_replacements()
    report = sq.query_state(ctx)
    assert not [d for d in report.drift if d.kind == "instance" and d.name == "test"]
    note = [n for n in report.notes if "instances/test" in n and "PENDING" in n]
    assert note and "ami-old" in note[0] and "ami-new" in note[0]

    ms.clear_pending_replacement("test")                         # the marker gone, the mismatch is drift
    drift = [d for d in sq.query_state(ctx).drift if d.kind == "instance" and d.name == "test"]
    assert drift and drift[0].drift == sq.DRIFT_CHANGED and "ami-new" in drift[0].detail
