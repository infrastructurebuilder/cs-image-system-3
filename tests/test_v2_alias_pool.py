# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 59: a pool of names, each spent once. The first free line of
`meta-state/aliases.txt` becomes a new durable machine's alias, recorded in
its launch parameters, and the line is commented out in place with what
took it and when -- before the machine exists. A dry run draws nothing and
says what it would take; a run that cannot launch draws nothing; an
ephemeral instance draws nothing; an empty pool is a warning and the launch
proceeds; a spent name never comes back. Validation refuses a free line a
machine could not take and reports how many remain. Stage 58 gives the
name to the machine as an AltNames entry.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from cs_image_system.base import alias_pool as ap
from cs_image_system.base import launch_params as lp
from cs_image_system.base import provider_aliases as pa
from cs_image_system.base.lifecycles import Lifecycle
from tests.v2_support import V2Run

POOL = "bright-otter\nquiet-heron\n\n# spent-eel  -- instance old as old-001 2026-09-21T10:00:00Z run r0\nred-cod\n"


def _seed(run: V2Run, text: str = POOL) -> Path:
    p = ap.pool_path(run.config_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def _inst(ctx, name="test"):
    return next(i for i in ctx.instances if i.get_name() == name)


@pytest.fixture
def real(tmp_path: Path, monkeypatch):
    """A real run whose instance roots may apply: the run that launches."""
    ap._DRAWN.clear()
    run = V2Run(tmp_path, monkeypatch, dry_run=False)
    run.ctx.config["apply_instances"] = True
    try:
        yield run
    finally:
        run.restore_cwd()


@pytest.fixture
def dry(tmp_path: Path, monkeypatch):
    ap._DRAWN.clear()
    run = V2Run(tmp_path, monkeypatch)
    try:
        yield run
    finally:
        run.restore_cwd()


# ------------------------------------------------------- the file itself

def test_the_pool_reads_free_and_spent_lines_and_ignores_blanks(tmp_path: Path):
    p = tmp_path / "aliases.txt"
    p.write_text(POOL)
    assert ap.free_names(p) == ["bright-otter", "quiet-heron", "red-cod"]
    assert ap.spent_names(p) == {"spent-eel": "instance old as old-001 2026-09-21T10:00:00Z run r0"}
    assert ap.peek(p) == "bright-otter"
    assert ap.free_names(tmp_path / "absent.txt") == [] and ap.peek(tmp_path / "absent.txt") is None


def test_a_draw_comments_the_first_free_line_out_in_place_with_the_record(tmp_path: Path):
    p = tmp_path / "aliases.txt"
    p.write_text(POOL)
    when = datetime(2026, 9, 22, 15, 4, 11, tzinfo=timezone.utc)
    assert ap.draw(p, taken_by="instance coops-model as coops-model-003", run_id="r1", when=when) == "bright-otter"
    lines = p.read_text().splitlines()
    assert lines[0] == "# bright-otter  -- instance coops-model as coops-model-003 2026-09-22T15:04:11Z run r1"
    assert lines[1:] == POOL.splitlines()[1:], "every other byte untouched"
    assert ap.free_names(p) == ["quiet-heron", "red-cod"]
    assert ap.spent_names(p)["bright-otter"].startswith("instance coops-model as coops-model-003")
    assert not p.with_suffix(".txt.tmp").exists(), "temp-then-replace"
    assert p.with_suffix(".txt.lock").exists(), "the lock file is the exclusive-draw seam"
    # the pool only ever shrinks: three draws, then nothing
    assert [ap.draw(p, taken_by="x", run_id="r") for _ in range(3)] == ["quiet-heron", "red-cod", None]
    assert ap.free_names(p) == []


def test_the_record_is_greppable_and_names_when_and_what():
    rec = ap.burn_record("instance test as test-002", "r7", datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
    assert rec == "instance test as test-002 2026-01-02T03:04:05Z run r7"


# ------------------------------------------------ the draw at generation

def test_a_new_durable_machine_takes_the_next_name_once_and_the_line_is_burned(real):
    ctx = real.ctx
    p = _seed(real)
    params = lp.compute_launch_params(ctx, _inst(ctx))
    assert params["alias"] == "bright-otter" and params["hostname"] == "test-001"
    assert ap.free_names(p) == ["quiet-heron", "red-cod"]
    burned = p.read_text().splitlines()[0]
    assert burned.startswith("# bright-otter  -- instance test as test-001 ") and f"run {ctx.run_id}" in burned
    # computed again in the same run: the same name, no second burn
    assert lp.compute_launch_params(ctx, _inst(ctx))["alias"] == "bright-otter"
    assert ap.free_names(p) == ["quiet-heron", "red-cod"]
    # the next new machine takes the next name
    assert lp.compute_launch_params(ctx, _inst(ctx, "test2"))["alias"] == "quiet-heron"
    # the after-generate recorder writes the alias into the launch record
    lp.record_launch_params(ctx, Lifecycle.INSTANCE_IMAGE)
    assert ctx.meta_state.launch_params()["test"]["alias"] == "bright-otter"


def test_a_standing_machine_keeps_its_recorded_alias_and_draws_nothing(real):
    ctx = real.ctx
    ms = ctx.meta_state
    p = _seed(real)
    rec = dict(ms.launch_params().get("test") or {})
    rec.update({"launched": True, "hostname": "test-001", "alias": "old-name"})
    ms.record_launch_params("test", rec)
    assert lp.compute_launch_params(ctx, _inst(ctx))["alias"] == "old-name"
    assert ap.free_names(p) == ["bright-otter", "quiet-heron", "red-cod"]


def test_a_replacement_is_a_new_machine_and_draws(real, monkeypatch):
    ctx = real.ctx
    ms = ctx.meta_state
    p = _seed(real)
    rec = dict(ms.launch_params().get("test") or {})
    rec.update({"launched": True, "hostname": "test-001", "alias": "old-name"})
    ms.record_launch_params("test", rec)
    monkeypatch.setattr(lp, "will_replace", lambda c, i: True)
    params = lp.compute_launch_params(ctx, _inst(ctx))
    assert params["alias"] == "bright-otter" and ap.free_names(p) == ["quiet-heron", "red-cod"]


def test_a_dry_run_draws_nothing_and_says_what_it_would_take(dry, caplog):
    ctx = dry.ctx
    p = _seed(dry)
    with caplog.at_level("INFO"):
        params = lp.compute_launch_params(ctx, _inst(ctx))
    assert "alias" not in params
    assert p.read_text() == POOL, "not a byte of the pool changed"
    assert any("would take alias 'bright-otter'" in r.message and "dry run" in r.message for r in caplog.records)


def test_a_run_that_cannot_launch_draws_nothing(real):
    ctx = real.ctx
    p = _seed(real)
    ctx.config["apply_instances"] = False
    assert "alias" not in lp.compute_launch_params(ctx, _inst(ctx))
    assert p.read_text() == POOL


def test_an_ephemeral_instance_draws_nothing(real, monkeypatch):
    ctx = real.ctx
    p = _seed(real)
    inst = _inst(ctx)
    monkeypatch.setattr(inst, "ephemeral", True, raising=False)
    assert "alias" not in lp.compute_launch_params(ctx, inst)
    assert p.read_text() == POOL


def test_no_file_means_no_aliases_and_no_error(real):
    ctx = real.ctx
    assert not ap.pool_path(real.config_root).exists()
    assert "alias" not in lp.compute_launch_params(ctx, _inst(ctx))


def test_an_empty_pool_is_a_warning_and_the_launch_proceeds(real, caplog):
    ctx = real.ctx
    _seed(real, "# spent-eel  -- instance old as old-001 2026-09-21T10:00:00Z run r0\n")
    with caplog.at_level("WARNING"):
        params = lp.compute_launch_params(ctx, _inst(ctx))
    assert "alias" not in params and params["hostname"] == "test-001"
    assert any("EMPTY" in r.message and "without an alias" in r.message for r in caplog.records)


# ---------------------------------------------------------- validation

def test_validate_refuses_a_free_line_a_machine_could_not_take_and_counts_the_rest(dry, caplog):
    from cs_image_system.base.commands.validate import check_alias_pool
    ctx = dry.ctx
    _seed(dry, "bright-otter\nNot A Label\nbright-otter\ntest\n" + "x" * 64 + "\n")
    errors = [str(e) for e in check_alias_pool(ctx)]
    assert any("line 2" in e and "'Not A Label'" in e for e in errors)
    assert any("line 3" in e and "repeats" in e for e in errors)
    assert any("line 4" in e and "already gives an instance" in e for e in errors)
    assert any("line 5" in e for e in errors)
    _seed(dry, POOL)
    with caplog.at_level("INFO"):
        assert check_alias_pool(ctx) == []
    assert any("3 name(s) remain" in r.message for r in caplog.records)
    _seed(dry, "# gone  -- instance x as x-001 2026-09-22T00:00:00Z run r\n")
    with caplog.at_level("WARNING"):
        assert check_alias_pool(ctx) == []
    assert any("EMPTY" in r.message for r in caplog.records)


def test_validate_is_silent_without_a_pool(dry):
    from cs_image_system.base.commands.validate import check_alias_pool
    assert check_alias_pool(dry.ctx) == []


# ------------------------------------------------- the name on the machine

def test_the_pool_alias_is_one_of_the_names_the_machine_answers_to():
    identity = {"instance_id": "i-1", "provider_hostname": "ip-10-0-0-1.internal"}
    assert pa.wanted_aliases(identity, "test-002", "test", "bright-otter") == ["test", "bright-otter", "ip-10-0-0-1"]
    assert pa.wanted_aliases(identity, "test-002", "test", "") == ["test", "ip-10-0-0-1"]
    assert "Bad Name" not in pa.wanted_aliases(identity, "test-002", "test", "Bad Name")


def test_the_alias_pass_writes_the_pool_name_onto_the_machine(real, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.base import power_state as ps
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    ctx = real.ctx
    ms = ctx.meta_state
    rec: dict[str, Any] = dict(ms.launch_params().get("test") or {"group": "coops"})
    rec.update({"launched": True, "hostname": "test-001", "alias": "bright-otter"})
    ms.record_launch_params("test", rec)
    scripts: list[tuple[str, str]] = []
    identity = {"instance_id": "i-1", "provider_hostname": "ip-10-0-0-1.internal"}
    monkeypatch.setattr(AwsCloudBuilder, "can_query_instance_identity", lambda s: True)
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_identity", lambda s, n: dict(identity) if n == "test" else None)
    monkeypatch.setattr(AwsCloudBuilder, "can_query_instance_power_state", lambda s: True)
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_power_state", lambda s, n: ps.RUNNING)
    monkeypatch.setattr(AwsCloudBuilder, "run_session_command",
                        lambda s, n, script, timeout=300: scripts.append((n, script)) or (0, "ALTNAMES_CHANGED"))
    monkeypatch.setattr(OktaTfGroupBuilder, "can_query_servers", lambda s: True)
    monkeypatch.setattr(OktaTfGroupBuilder, "registered_servers",
                        lambda s, g: [{"id": "live", "hostname": "test-001", "instance_id": "i-1", "alt_names": []}])
    pa.register_provider_aliases(ctx, Lifecycle.INSTANCE_IMAGE)
    written = [s for n, s in scripts if n == "test" and s != "true"]
    assert len(written) == 1 and "  - bright-otter" in written[0] and "  - ip-10-0-0-1" in written[0]
