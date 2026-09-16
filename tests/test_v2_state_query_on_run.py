# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Decision 2026-08-27: every run first asks reality (read-only) and refuses
to proceed on hard drift; providers that cannot answer are reported, not
fatal; --no-state-query keeps the existing report."""
from __future__ import annotations

import json

import pytest

from tests.v2_support import V2Run

from cs_image_system.base import state_query as sq


@pytest.fixture
def stubbed(monkeypatch):
    """Image hook answering from canned reality, installed AFTER V2Run's own
    stubs (call ``stubbed(run)``)."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    reality: dict = {"images": {}, "fail_images": False}

    def install(run):
        def images(self, series):
            if reality["fail_images"]:
                raise RuntimeError("no credentials")
            return list(reality["images"].get(self.get_name(), []))
        monkeypatch.setattr(AwsCloudBuilder, "query_images", images)
        return reality
    reality["install"] = install
    return reality


def test_run_queries_state_first_and_records_it(tmp_path, monkeypatch, stubbed):
    run = V2Run(tmp_path, monkeypatch)
    stubbed["install"](run)
    try:
        summary = run.run("identity", apply=False, state_query=True)
        assert summary.ok, summary.error
        assert summary.state == {"missing": 0, "foreign": 0, "changed": 0, "stale": 0, "unavailable": 0, "hard": 0}
        report = json.loads(sq.state_report_path(run.ctx).read_text())
        assert report["run"] == run.ctx.run_id
        assert "state" in summary.to_dict()
    finally:
        run.restore_cwd()


def test_hard_drift_refuses_the_run(tmp_path, monkeypatch, stubbed):
    run = V2Run(tmp_path, monkeypatch)
    try:
        ms = run.ctx.meta_state
        ms.add_build({"build_id": "ami-gone", "series": "basic-rh-10", "runtime": "aws-east2-runtime",
                      "name": "x", "parent": "vendor", "input_fingerprint": "f", "run": "r0",
                      "capabilities": {"identity_types": [], "storage_types": []}, "mods": [], "chain": []})
        ms.bind_instance("test2", "ami-gone", "r0")          # pinned to a build reality no longer has
        summary = run.run("identity", apply=False, state_query=True)
        assert not summary.ok
        assert summary.state and summary.state["hard"] == 1 and summary.state["missing"] == 1
        assert any("ami-gone" in e and "PINNED" in e for e in summary.validation_errors)
        # the operator can still run with the previous belief, explicitly
        sq.state_report_path(run.ctx).unlink()
        summary2 = run.run("identity", apply=False, state_query=False)
        assert summary2.ok and summary2.state is None
    finally:
        run.restore_cwd()


def test_unavailable_provider_does_not_block(tmp_path, monkeypatch, stubbed):
    stubbed["fail_images"] = True
    run = V2Run(tmp_path, monkeypatch)
    stubbed["install"](run)
    try:
        summary = run.run("identity", apply=False, state_query=True)
        assert summary.ok, summary.error
        assert summary.state and summary.state["unavailable"] >= 1 and summary.state["hard"] == 0
        report = json.loads(sq.state_report_path(run.ctx).read_text())
        assert any("no credentials" in u for u in report["unavailable"])
    finally:
        run.restore_cwd()
