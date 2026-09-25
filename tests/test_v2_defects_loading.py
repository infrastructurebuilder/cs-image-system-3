# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 63, the medium items that live at load (15, 16, 18, 19): an alias on
a modification item, the bash ``ensure`` entries, the read-only group
builder's hooks, and ``use_state_backends: false``. Decided by the operator
2026-09-25; every test here failed before its fix.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.v2_support import V2Run, copy_config, load_context, reset_singletons, stub_environment


def _edit_yaml(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


# ------------------------------------ 15. an alias on a modification's type

def _alias_the_bash_item(root: Path) -> None:
    def edit(data):
        for image in data["images"]:
            for mod in image.get("modifications") or []:
                if mod.get("type") == "bash-remote":
                    mod["type"] = "bash"            # the fixture builder's alias
    _edit_yaml(root / "images" / "image1.yaml", edit)


def test_an_alias_on_a_modification_type_is_rewritten_to_the_builders_name(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _alias_the_bash_item(root)
    assert "type: bash\n" in (root / "images" / "image1.yaml").read_text()
    stub_environment(monkeypatch)
    ctx = load_context(root)
    mods = [m for image in ctx.images for m in (image.modifications or [])
            if m.get_name() == "derivative-setup"]
    assert mods, "the fixture's bash item is gone"
    assert {m.get_type() for m in mods} == {"bash-remote"}
    reset_singletons()


def test_an_aliased_modification_generates(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _alias_the_bash_item(root)
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        summary = run.run(["base-image", "instance-image"], apply=False)
        assert summary.ok, summary.error
    finally:
        run.restore_cwd()


# ----------------------------------------- 16. the bash `ensure` entries

@pytest.mark.parametrize("ensure, needle", [
    ({"packages": "git"}, "ensure.packages must be a list of package names"),
    ({"services": "chronyd"}, "ensure.services must be a list of systemd unit names"),
    ({"packages": ["git", ""]}, "ensure.packages[1] must be a non-empty name"),
    ({"files": [{"content": "x"}]}, "ensure.files[0]: `path` is required"),
    ({"files": [{"path": "/a", "owner": "root"}]}, "ensure.files[0]: unknown keys ['owner']"),
    ({"files": [{"path": "/a", "mode": "rw-r--r--"}]}, "must be three or four octal digits"),
    ({"files": [{"path": "/a", "mode": 644}]}, "quote it"),
    ({"files": ["/a"]}, "ensure.files[0] must be a mapping"),
    ({"commands": [{"unless": "true"}]}, "ensure.commands[0]: `run` is required"),
    ({"commands": [{"run": "x", "when": "y"}]}, "unknown keys ['when']"),
    ({"packages": [], "files": []}, "every one is empty"),
    ({"users": ["x"]}, "unknown ensure keys ['users']"),
])
def test_a_malformed_ensure_entry_is_refused_at_load_by_name(ensure, needle):
    from cs_image_system.bash_mod_plugin.bash_models import validate_ensure
    with pytest.raises(ValueError) as exc:
        validate_ensure("derivative-setup", ensure)
    assert needle in str(exc.value), str(exc.value)
    assert "derivative-setup" in str(exc.value)


def test_a_valid_ensure_comes_back_unchanged_so_no_fingerprint_moves():
    from cs_image_system.bash_mod_plugin.bash_models import validate_ensure
    ensure = {"packages": ["git"], "files": [{"path": "/etc/x.conf", "content": "a\n", "mode": "0644"}],
              "services": ["chronyd"], "commands": [{"run": "mkdir -p /d", "unless": "test -d /d"}]}
    assert validate_ensure("m", ensure) == ensure


def test_an_unquoted_octal_mode_renders_as_octal_not_decimal():
    from cs_image_system.bash_mod_plugin.bash_models import validate_ensure
    parsed = yaml.safe_load("files:\n  - path: /etc/x.conf\n    mode: 0644\n")
    assert parsed["files"][0]["mode"] == 420               # what YAML hands the loader
    out = validate_ensure("m", parsed)
    assert out["files"][0]["mode"] == "0644"


def _bash_item(**kw):
    from cs_image_system.bash_mod_plugin.bash_models import BashModItemModel
    return BashModItemModel(name="m", **kw)


def test_the_item_renders_an_integer_mode_in_octal_and_stops_at_the_first_package_manager():
    item = _bash_item(ensure={"packages": ["git"], "files": [{"path": "/etc/x.conf", "content": "a", "mode": 0o640}]})
    lines = item.ensure_lines()
    assert any("install -m 0640 " in ln for ln in lines), lines
    pkg = next(ln for ln in lines if ln.startswith("for p in git;"))
    assert "if command -v dnf" in pkg and "elif command -v yum" in pkg and "elif command -v apt-get" in pkg
    assert "no dnf, yum or apt-get" in pkg and pkg.rstrip().endswith("|| exit 1; done")


def test_the_package_line_installs_with_the_first_manager_and_fails_with_its_error(tmp_path: Path):
    """Run the emitted line against fake package managers: dnf exists and
    fails, and apt-get (which also exists) must never be tried."""
    import os
    import subprocess
    item = _bash_item(ensure={"packages": ["nosuchpkg"]})
    line = next(ln for ln in item.ensure_lines() if ln.startswith("for p in"))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    journal = tmp_path / "journal"
    for name, rc in (("rpm", 1), ("dpkg", 1), ("dnf", 3), ("apt-get", 0)):
        f = bindir / name
        f.write_text(f"#!/bin/sh\necho {name} \"$@\" >> {journal}\nexit {rc}\n")
        f.chmod(0o755)
    sudo = bindir / "sudo"
    sudo.write_text('#!/bin/sh\nexec "$@"\n')
    sudo.chmod(0o755)
    env = {**os.environ, "PATH": f"{bindir}:/usr/bin:/bin"}
    res = subprocess.run(["/bin/sh", "-c", line], env=env, capture_output=True, text=True)
    assert res.returncode == 1, res
    ran = journal.read_text()
    assert "dnf -y install nosuchpkg" in ran and "apt-get" not in ran, ran


# ------------------------------ 18. the read-only group builder's hooks

def test_the_read_only_group_builder_answers_the_read_only_truth(monkeypatch):
    from tests.v2_support import FIXTURE_CONFIG
    from cs_image_system.base.read_models import identity_read_model
    stub_environment(monkeypatch)
    ctx = load_context(FIXTURE_CONFIG)
    try:
        ro = ctx.group_builders["okta-groups-ro"]
        managed = ctx.group_builders["oktagroups"]
        assert [g.get_name() for g in ro.get_groups_for_builder()] == ["readers"]
        assert ro.manages_groups() is False and managed.manages_groups() is True

        def no_opa(*a, **kw):
            raise AssertionError("the read-only builder asked OPA")
        monkeypatch.setattr(type(ro), "_resolver", no_opa)
        assert ro.query_state() == {}
        assert ro.enrollment_token_reference("readers") is None
        assert ro.can_query_servers() is False
        assert ro.can_manage_workload_access() is False
        with pytest.raises(NotImplementedError):
            ro.query_attributes(ro.get_groups_for_builder()[0])
        with pytest.raises(NotImplementedError):
            ro.attribute_conflicts()

        model = identity_read_model(ctx)["groups"]
        assert model["readers"]["managed"] is False and model["readers"]["builder"] == "okta-groups-ro"
        assert model["coops"]["managed"] is True
    finally:
        reset_singletons()


def test_a_read_only_group_is_looked_up_and_never_drifts(tmp_path: Path, monkeypatch):
    from cs_image_system.base import state_query
    from cs_image_system.base.state_query import StateReport
    run = V2Run(tmp_path, monkeypatch)
    try:
        summary = run.run(["identity"], apply=False)
        assert summary.ok, summary.error
        data_tf = "".join(p.read_text() for p in run.generated.rglob("*.tf") if "okta-groups-ro" in str(p))
        assert 'data "okta_group"' in data_tf and '"readers"' in data_tf, "the lookup root emits the lookup"
        assert "module \"group_readers\"" not in "".join(p.read_text() for p in run.generated.rglob("*.tf"))
        # the managed parent's rule would read an absent OPA record as missing [HARD]
        recorded = run.ctx.meta_state.identity_read_model()["groups"]
        assert recorded["readers"]["managed"] is False, "the run's read-model records the lookup as unmanaged"
        report = StateReport(run="test")
        drift = state_query.group_drift(run.ctx, {"readers": {"present": False}}, report)
        assert not [d for d in drift if d.name == "readers"], drift
    finally:
        run.restore_cwd()


# --------------------------- 19. use_state_backends: false with a producer

def _state_backend_errors(root: Path, monkeypatch) -> list[str]:
    from cs_image_system.base.commands.validate import collect_validation_errors
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        return [str(e) for e in collect_validation_errors(ctx) if "use_state_backends" in str(e)]
    finally:
        reset_singletons()


def _set_flag(root: Path, value: bool) -> None:
    cfg = root / "cfg" / "_config.yml"
    text = cfg.read_text()
    assert "use_state_backends: true" in text
    cfg.write_text(text.replace("use_state_backends: true", f"use_state_backends: {str(value).lower()}"))


def test_the_flag_off_is_refused_naming_every_root_that_reads_a_producer(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _set_flag(root, False)
    errors = _state_backend_errors(root, monkeypatch)
    assert errors, "the flag off loaded and validated with roots that read remote state"
    import re
    consumers = {re.search(r"the root '([^']+)'", e).group(1) for e in errors}   # type: ignore[union-attr]
    # both instance roots read the storage roots and the identity root; the
    # three storage roots whose storages carry group gids read the identity root
    assert consumers == {"open-tofu", "tofu-gce", "aws-ebs", "aws-efs", "gcp-pd"}, errors
    by_root = {re.search(r"the root '([^']+)'", e).group(1): e for e in errors}   # type: ignore[union-attr]
    assert "'oktagroups'" in by_root["aws-ebs"] and "'aws-ebs'" in by_root["open-tofu"]
    assert all("set use_state_backends: true" in e for e in errors)


def test_the_flag_on_raises_nothing(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    assert _state_backend_errors(root, monkeypatch) == []
