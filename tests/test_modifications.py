# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Modifications: shell and ansible items, their builders, the ``ensure``
form and the on-image bundle.

* an image carrying both an ansible mod and a bash mod (inline lines and a
  script file) generates one ``provisioner "ansible"`` and well-formed
  ``provisioner "shell"`` blocks, the script file copied beside the packer
  root; the item's ``type:`` selects the mod builder (an alias is rewritten
  to the builder's name at load; an unknown type hard-fails); lineage
  records both mods with content hashes;
* every instance-image bake stages a modification bundle beside the packer
  root and installs it on the image at /opt/csis/mods with a ``csis-mods``
  runner (list / rerun); the bundle's manifests are the lineage mod
  records;
* bash mods take a declarative ``ensure:`` form that generates guarded
  (idempotent) shell, validated at load by name; idempotence is recorded
  per mod in lineage; the on-image bundle replays the ensure lines first;
* the ansible builder escapes its strings and its ``configuration_user``
  wins; a missing playbook and a modification with no builder are named
  refusals; the bash builder runs the lines as its ``configuration_user``
  and refuses ``execute_command`` beside it, and ``extra_arguments``.

Origins: gate 8 (DESIGN §3M2), EXPLORE "Locally Installing Modifications"
and "Generation of Idempotent Script-based Modifications".

history: stage 63 items 15 and 16 and the ansible/bash dead-code items.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from harness import V2Run, copy_config, load_context, stub_environment

BUILD = Path("instance-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-build.pkr.hcl")


@pytest.fixture
def v2(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    yield run
    run.restore_cwd()


def _dask_section(build: str) -> str:
    """Everything emitted for imgfile-basic-dask (up to the next image's mods)."""
    start = build.index("# Modifications for dask-setup-jeffy")
    end = build.index("# Modifications for data-science-setup")
    return build[start:end]


def test_both_modification_kinds_are_emitted_as_provisioners(v2):
    assert v2.run(["instance-image"], apply=False).ok
    build = (v2.generated / BUILD).read_text()
    sect = _dask_section(build)
    # ansible
    assert 'provisioner "ansible" {' in sect and 'playbook_file = "setup_dask.yml"' in sect
    # bash: the mod's script file and its inline lines are two shell
    # provisioners (packer forbids scripts+inline in one block), files first;
    # the image's identity activation is a separate, later shell provisioner
    assert sect.count("(shell)") == 1
    assert "# Modifications for derivative-setup of type bash-remote (shell)" in sect
    assert sect.index("(shell)") < sect.index("identity activation")
    mod_blocks = sect[sect.index("(shell)"):sect.index("identity activation")]
    assert mod_blocks.count('provisioner "shell" {') == 2
    assert mod_blocks.index("scripts = [") < mod_blocks.index("inline = [")
    assert 'only = ["amazon-ebs.imgfile-basic-dask"]' in sect
    assert 'scripts = ["mod_image.sh"]' in sect
    assert "sudo mkdir -p /opt/derivative" in sect
    assert "echo 'derivative setup'" in sect
    # no raw script lines outside a provisioner, no stray exit
    assert "\nexit 0" not in build
    assert build.count("provisioner ") == build.count("provisioner \"")
    # the script file was copied beside the packer root
    assert (v2.generated / BUILD.parent / "mod_image.sh").is_file()
    # ansible mods elsewhere are untouched
    assert build.count('provisioner "ansible" {') == 2


def test_unknown_modification_type_is_a_hard_failure(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    p = root / "images" / "image1.yaml"
    data = yaml.safe_load(p.read_text())
    dask = next(i for i in data["images"] if i["name"] == "imgfile-basic-dask")
    dask["modifications"][1]["type"] = "powershell-remote"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    with pytest.raises(KeyError, match="powershell-remote"):
        V2Run(tmp_path, monkeypatch, config_root=root)


def test_bash_item_requires_script_or_scripts():
    from cs_image_system.bash_mod_plugin.bash_models import BashModItemModel
    with pytest.raises(ValueError, match="must supply 'script'"):
        BashModItemModel(name="empty", type_="bash-remote")
    m = BashModItemModel(name="ok", type_="bash-remote", scripts=["a.sh"], script=[" ", "echo hi"])
    assert m.script == ["echo hi"] and m.scripts == ["a.sh"]
    m.remap_self_with_copied_assets({"a.sh": Path("copied/a.sh")})
    assert m.scripts == ["copied/a.sh"]


def test_lineage_records_both_mods_with_content_hashes(v2):
    assert v2.run(["instance-image"], apply=False).ok
    ctx = v2.ctx
    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.contract.lifecycles import Lifecycle
    d = v2.generated / BUILD.parent
    (d / "manifest.json").write_text(json.dumps({"last_run_uuid": "u", "builds": [
        {"name": "imgfile-basic-dask", "packer_run_uuid": "u", "artifact_id": "us-east-2:ami-0dask0001"}]}))
    ctx.current_lifecycle = Lifecycle.INSTANCE_IMAGE
    ctx.image_builders["pckr-ebs-ans"].post_finalize_phase(ExecutionLifecyclePhase.IMAGE_GENERATION)
    ctx.current_lifecycle = None
    build = next(b for b in yaml.safe_load((v2.meta_state / "lineage.yaml").read_text())["builds"]
                 if b["build_id"] == "ami-0dask0001")
    mods = {m["name"]: m for m in build["mods"]}
    assert mods["dask-setup-jeffy"]["operation"] == "ansible"
    assert mods["derivative-setup"]["operation"] == "bash"
    assert mods["derivative-setup"]["type"] == "bash-remote"
    assert re.fullmatch(r"[0-9a-f]{64}", mods["derivative-setup"]["content_hash"])
    assert mods["derivative-setup"]["content_hash"] != mods["dask-setup-jeffy"]["content_hash"]


# ------------------------------------------------- the local modification bundle

BLOCK = Path("instance-image/pckr-ebs-ans/image-generation/block-000")


def test_bundle_is_staged_and_installed(v2):
    assert v2.run(["base-image", "instance-image"], apply=False).ok
    bundle = v2.generated / BLOCK / "csis-mods" / "imgfile-basic-dask"
    assert (bundle / "csis-mods").is_file()
    dirs = sorted(p.name for p in bundle.iterdir() if p.is_dir())
    assert dirs == ["01-dask-setup-jeffy", "02-derivative-setup"]
    assert (bundle / "01-dask-setup-jeffy" / "setup_dask.yml").is_file()
    assert "ansible-playbook -i localhost, -c local 'setup_dask.yml'" in (bundle / "01-dask-setup-jeffy" / "run.sh").read_text()
    d2 = bundle / "02-derivative-setup"
    assert (d2 / "mod_image.sh").is_file() and (d2 / "inline.sh").is_file()
    run_sh = (d2 / "run.sh").read_text()
    assert "sh 'mod_image.sh'" in run_sh and "sh ./inline.sh" in run_sh
    m = yaml.safe_load((d2 / "MANIFEST.yaml").read_text())
    assert m["operation"] == "bash" and m["idempotent"] == "unknown"
    assert sorted(m["files"]) == ["inline.sh", "mod_image.sh"]
    index = yaml.safe_load((bundle / "MANIFEST.yaml").read_text())
    assert [x["dir"] for x in index["mods"]] == dirs
    build = (v2.generated / BLOCK / "pckr-ebs-ans-image-generation-block-000-build.pkr.hcl").read_text()
    assert 'source      = "csis-mods/imgfile-basic-dask/"' in build
    assert "sudo mv /tmp/csis-mods /opt/csis/mods" in build
    assert "/usr/local/bin/csis-mods" in build
    # installed after the image's own mods and its activation
    sect = build[build.index('only = ["amazon-ebs.imgfile-basic-dask"]'):]
    assert sect.index("tx.group: coops") < sect.index("local modification bundle for imgfile-basic-dask")
    # base images carry no bundle
    assert "csis-mods" not in (v2.generated / "base-image" / "pckr-ebs-ans" / "image-generation" / "block-000"
                               / "pckr-ebs-ans-image-generation-block-000-build.pkr.hcl").read_text()


def test_runner_script_lists_and_reruns_in_order(v2, tmp_path):
    assert v2.run(["instance-image"], apply=False).ok
    bundle = v2.generated / BLOCK / "csis-mods" / "imgfile-basic-dask"
    # replace the real run.sh wrappers with journaling stubs and exercise the runner
    journal = tmp_path / "journal"
    for d in bundle.iterdir():
        if d.is_dir():
            (d / "run.sh").write_text(f"#!/bin/sh\necho {d.name} >> '{journal}'\n")
    env = {"CSIS_MODS_ROOT": str(bundle), "PATH": "/usr/bin:/bin"}
    out = subprocess.run(["sh", str(bundle / "csis-mods"), "list"], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.split() == ["01-dask-setup-jeffy", "02-derivative-setup"]
    subprocess.run(["sh", str(bundle / "csis-mods"), "rerun"], env=env, check=True)
    assert journal.read_text().split() == ["01-dask-setup-jeffy", "02-derivative-setup"]
    journal.unlink()
    subprocess.run(["sh", str(bundle / "csis-mods"), "rerun", "derivative-setup"], env=env, check=True)
    assert journal.read_text().split() == ["02-derivative-setup"]
    assert subprocess.run(["sh", str(bundle / "csis-mods"), "bogus"], env=env, capture_output=True).returncode == 2


def test_ensure_generates_guarded_shell(v2):
    assert v2.run(["instance-image"], apply=False).ok
    build = (v2.generated / BLOCK / "pckr-ebs-ans-image-generation-block-000-build.pkr.hcl").read_text()
    assert "rpm -q" in build and "dnf -y install" in build          # packages guarded by a query
    assert "cmp -s /tmp/.csis-ensure '/etc/derivative.conf'" in build   # files replaced only when different
    assert "( test -d /opt/derivative/data ) >/dev/null 2>&1 || { sudo mkdir -p /opt/derivative/data; }" in build
    # the inline steps: ensure lines come first, then the free-form lines
    assert build.index("rpm -q") < build.index("echo 'derivative setup'")


def test_idempotence_is_declared_and_recorded():
    from cs_image_system.bash_mod_plugin.bash_models import BashModItemModel
    declared = BashModItemModel(name="d", type_="bash-remote", ensure={"packages": ["git"]})
    assert declared.idempotent == "declared"
    mixed = BashModItemModel(name="m", type_="bash-remote", ensure={"packages": ["git"]}, script=["true"])
    assert mixed.idempotent == "unknown"
    with pytest.raises(ValueError, match="unknown ensure keys"):
        BashModItemModel(name="x", type_="bash-remote", ensure={"users": ["a"]})
    with pytest.raises(ValueError, match="must supply"):
        BashModItemModel(name="x", type_="bash-remote")
    lines = declared.ensure_lines()
    assert lines and lines[0].startswith("for p in git; do rpm -q")


def test_lineage_records_idempotence_and_bundle(v2):
    assert v2.run(["instance-image"], apply=False).ok
    ctx = v2.ctx
    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.contract.lifecycles import Lifecycle
    (v2.generated / BLOCK / "manifest.json").write_text(json.dumps({"last_run_uuid": "u", "builds": [
        {"name": "imgfile-basic-dask", "packer_run_uuid": "u", "artifact_id": "us-east-2:ami-0dask0001"}]}))
    ctx.current_lifecycle = Lifecycle.INSTANCE_IMAGE
    ctx.image_builders["pckr-ebs-ans"].post_finalize_phase(ExecutionLifecyclePhase.IMAGE_GENERATION)
    ctx.current_lifecycle = None
    build = next(b for b in yaml.safe_load((v2.meta_state / "lineage.yaml").read_text())["builds"]
                 if b["build_id"] == "ami-0dask0001")
    assert build["local_mods"] is True
    mods = {m["name"]: m for m in build["mods"]}
    assert mods["dask-setup-jeffy"]["idempotent"] == "ansible"
    assert mods["derivative-setup"]["idempotent"] == "unknown"   # ensure + free-form lines


# ------------------------------------------------- an alias on a modification's type

def _edit_yaml(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


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
    mods: list[Any] = [m for image in ctx.images for m in (image.modifications or [])
                       if not isinstance(m, dict) and m.get_name() == "derivative-setup"]
    assert mods, "the fixture's bash item is gone"
    assert {m.get_type() for m in mods} == {"bash-remote"}


def test_an_aliased_modification_generates(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _alias_the_bash_item(root)
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        summary = run.run(["base-image", "instance-image"], apply=False)
        assert summary.ok, summary.error
    finally:
        run.restore_cwd()


# ------------------------------------------------- the bash ensure entries

@pytest.mark.parametrize("ensure, needle", [
    ({"packages": "git"}, "ensure.packages"),
    ({"services": "chronyd"}, "ensure.services"),
    ({"packages": ["git", ""]}, "ensure.packages[1]"),
    ({"files": [{"content": "x"}]}, "`path`"),
    ({"files": [{"path": "/a", "owner": "root"}]}, "['owner']"),
    ({"files": [{"path": "/a", "mode": "rw-r--r--"}]}, "octal"),
    ({"files": [{"path": "/a", "mode": 644}]}, "quote"),
    ({"files": ["/a"]}, "ensure.files[0]"),
    ({"commands": [{"unless": "true"}]}, "`run`"),
    ({"commands": [{"run": "x", "when": "y"}]}, "['when']"),
    ({"packages": [], "files": []}, "empty"),
    ({"users": ["x"]}, "['users']"),
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


# ------------------------------------------------- the ansible and bash builders

def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _mod_builder(data: dict, name: str) -> dict:
    return next(b for b in data["mod_builders"] if b["name"] == name)


def test_ansible_strings_are_escaped_and_the_user_override_wins(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "mod-builders.yml", lambda d: _mod_builder(d, "ansible-default").update(
        extra_arguments=['--extra-vars', 'motd="hello"'], configuration_user="deployer"))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["base-image", "instance-image"], apply=False).ok
        text = "".join(p.read_text() for p in run.generated.rglob("*build.pkr.hcl") if "instance-image" in str(p))
        assert '"motd=\\"hello\\""' in text, "a quote inside an argument is escaped"
        assert 'user = "deployer"' in text and 'user = "packer"' not in text, "configuration_user wins"
    finally:
        run.restore_cwd()


def test_a_missing_playbook_is_refused_at_generation(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)

    def edit(d):
        dask = next(i for i in d["images"] if i["name"] == "imgfile-basic-dask")
        mod = next(m for m in dask["modifications"] if m.get("playbooks"))
        mod["playbooks"] = ["no-such-playbook.yml"]
    _edit(root / "images" / "image1.yaml", edit)
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        summary = run.run(["base-image", "instance-image"], apply=False)
        assert not summary.ok and "no-such-playbook.yml" in str(summary.error), summary.error
    finally:
        run.restore_cwd()


def test_a_modification_with_no_builder_and_no_default_is_a_named_refusal(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "mod-builders.yml", lambda d: _mod_builder(d, "ansible-default").update(is_default=False))
    stub_environment(monkeypatch)
    with pytest.raises(Exception) as exc:
        load_context(root)
    # refused by name at load (the builder-list check fires first; the
    # orchestrator's own refusal covers an item that reaches it anyway),
    # never an AttributeError at generation
    message = str(exc.value)
    assert "builder" in message and "AttributeError" not in message, message


def test_bash_configuration_user_runs_the_lines_as_that_user(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "mod-builders.yml",
          lambda d: _mod_builder(d, "bash-remote").update(configuration_user="modder"))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["base-image", "instance-image"], apply=False).ok
        text = "".join(p.read_text() for p in run.generated.rglob("*build.pkr.hcl") if "instance-image" in str(p))
        assert "sudo su - modder -c" in text, "the shell provisioner runs the item as the user"
    finally:
        run.restore_cwd()


def test_bash_configuration_user_and_execute_command_together_are_refused():
    from cs_image_system.bash_mod_plugin.bash_models import BashModBuilderModel
    with pytest.raises(Exception, match="declare one"):
        cast(Any, BashModBuilderModel)(name="b", type="bash-remote", configuration_user="u", execute_command="x")


def test_bash_extra_arguments_is_refused():
    from cs_image_system.bash_mod_plugin.bash_models import BashModBuilderModel
    with pytest.raises(Exception, match="extra_arguments"):
        cast(Any, BashModBuilderModel)(name="b", type="bash-remote", extra_arguments=["-x"])


def test_the_on_image_bundle_replays_the_ensure_lines_first(tmp_path: Path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run(["base-image", "instance-image"], apply=False).ok
        scripts = [p for p in run.generated.rglob("inline.sh") if "derivative-setup" in str(p)]
        assert scripts, "the bundle carries the derivative-setup item"
        body = scripts[0].read_text()
        assert "for p in git;" in body and body.index("for p in git;") < body.index("echo 'derivative setup'"), body
    finally:
        run.restore_cwd()
