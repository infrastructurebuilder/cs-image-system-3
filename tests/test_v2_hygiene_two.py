# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 43, hygiene bundle II -- the small things noted since stage 39, each
pinned here with its own proof: a run commits no run-local file (and drops
one an older tree tracked); a modification item with nothing to modify with
is refused by name; every runtime's default image builder names a declared
one; `validate` says what it cannot check once, as information; the
`--only-runtime` help says what the flag does; the tofu lock refuses a second
holder and releases on any exit.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from cs_image_system.base.constants import RUN_LOCAL_FILENAMES
from cs_image_system.base.meta_state import commit_meta_state
from v2_support import FIXTURE_CONFIG, REPO

GOLDEN = REPO / "tests" / "fixtures" / "v2_golden"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


# --------------------------------------------------------- 43.1 run-local files

def test_the_root_ignore_names_the_run_local_files_and_lifecycle_ignores_do_not():
    root = (GOLDEN / "generated" / ".gitignore").read_text().split()
    for name in RUN_LOCAL_FILENAMES:
        assert name in root, name
    assert "final_execution.sh" not in root                                  # a record: committed
    for lc in ("identity", "storage", "release", "retention"):
        lines = (GOLDEN / "generated" / lc / ".gitignore").read_text().split()
        assert not any(n in lines for n in RUN_LOCAL_FILENAMES), lc


def test_a_run_commit_drops_tracked_run_local_files_and_never_stages_them(tmp_path):
    """The live configuration tracked both files; the strict query rewrites the
    report outside any run, so every preflight dirtied the checkout. One run's
    commit removes them from the index, leaves them on disk, and never stages
    them again; the records beside them stay tracked."""
    repo = tmp_path / "cfg"
    generated = repo / "generated"
    root_dir = generated / "identity" / "ws"
    root_dir.mkdir(parents=True)
    (repo / "meta-state").mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "config", "user.email", "t@example.org")
    _git(repo, "config", "user.name", "t")
    (repo / "meta-state" / "runs.yaml").write_text("runs: []\n")
    (generated / "final_execution.sh").write_text("#!/bin/sh\n")
    (root_dir / "main.tf").write_text("locals { v = 1 }\n")
    for name in RUN_LOCAL_FILENAMES:
        (generated / name).write_text('{"older": true}\n')
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "an older tree that tracked the run-local files")
    assert {f"generated/{n}" for n in RUN_LOCAL_FILENAMES} <= set(_git(repo, "ls-files").split())

    # the next run: fresh run-local content, one real change, the emitted ignore line
    for name in RUN_LOCAL_FILENAMES:
        (generated / name).write_text('{"run": "run1"}\n')
    (root_dir / "main.tf").write_text("locals { v = 2 }\n")
    (generated / ".gitignore").write_text("".join(f"{n}\n" for n in RUN_LOCAL_FILENAMES))
    sha = commit_meta_state(repo, generated, "run1", ["identity"], dry_run=True)
    assert sha
    changes = _git(repo, "show", "--name-status", "--format=", "HEAD").split("\n")
    for name in RUN_LOCAL_FILENAMES:
        assert f"D\tgenerated/{name}" in changes, changes
    assert "M\tgenerated/identity/ws/main.tf" in changes and "A\tgenerated/.gitignore" in changes
    tracked = _git(repo, "ls-files").split()
    assert not any(p.endswith(RUN_LOCAL_FILENAMES) for p in tracked)
    assert "generated/final_execution.sh" in tracked and "meta-state/runs.yaml" in tracked
    for name in RUN_LOCAL_FILENAMES:
        assert (generated / name).read_text() == '{"run": "run1"}\n'        # on disk, untouched
    assert _git(repo, "status", "--porcelain") == ""                         # clean: nothing dirty, nothing staged
    assert commit_meta_state(repo, generated, "run2", ["identity"], dry_run=True) is None


# ------------------------------------------- 43.2 a modification with nothing to modify with

def test_an_ansible_item_without_playbooks_is_refused_by_name():
    from cs_image_system.ansible_plugin.ansible_models import AnsibleModItemModel
    with pytest.raises(ValueError, match="dask-setup2") as e:
        AnsibleModItemModel(name="dask-setup2", type_="ansible-default", config={"dask_version": "2023.9.1"})
    assert "no playbooks" in str(e.value) and "nothing to modify with" in str(e.value)
    ok = AnsibleModItemModel(name="dask-setup", type_="ansible-default", playbooks=["setup_dask.yml"])
    assert ok.playbooks == ["setup_dask.yml"]


def test_no_fixture_image_declares_a_modification_with_nothing_to_run():
    for path in (FIXTURE_CONFIG / "images").glob("*.yaml"):
        for image in yaml.safe_load(path.read_text()).get("images") or []:
            for item in image.get("modifications") or []:
                assert item.get("playbooks") or item.get("script") or item.get("scripts") or item.get("ensure"), \
                    f"{path.name}: {image['name']} / {item['name']}"


# --------------------------------------------------- 43.5 warnings printed for no one

def test_every_runtime_default_image_builder_names_a_declared_image_builder():
    """The fixture named `packer-gcloud-ansible`, which no image builder
    declares; the FK warning it raised on every run was printed for no one."""
    builders = {b["name"] for b in yaml.safe_load((FIXTURE_CONFIG / "cfg" / "image-builders.yml").read_text())["image_builders"]}
    runtimes = yaml.safe_load((FIXTURE_CONFIG / "cfg" / "runtime-builders.yml").read_text())["runtime_builders"]
    assert runtimes
    for rt in runtimes:
        ref = rt.get("default_image_builder")
        assert ref in (None, "default") or ref in builders, f"{rt['name']}: {ref!r} is not a declared image builder"


def test_validate_says_what_it_cannot_check_once_as_information(caplog):
    """stage 43: a provider without an executable is information, not a
    warning apiece (the tools themselves are checked since stage 48.1)."""
    from cs_image_system.base.commands.validate import check_existence_of_executable
    unspecified: list[str] = []
    with caplog.at_level(logging.DEBUG):
        providers = {"aws-east2-runtime": SimpleNamespace(model=SimpleNamespace(executable=None), type_="aws")}
        assert check_existence_of_executable({}, providers, unspecified=unspecified) == []   # type: ignore[arg-type]
    assert unspecified == ["aws-east2-runtime (aws)"]
    assert not [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


# ------------------------------------------------- 43.7 help that says what the flag does

def test_only_runtime_help_says_it_scopes_the_terraform_roots_too():
    """Read from the command object: invoking `run --help` would first run the
    CLI callback, which loads a configuration from the working directory."""
    import typer.main
    from cs_image_system.system.cli import app
    run = typer.main.get_command(app).commands["run"]                        # type: ignore[attr-defined]
    helps = {opt: (p.help or "") for p in run.params for opt in (getattr(p, "opts", None) or [])}
    assert "terraform roots" in helps["--only-runtime"] and "emit nothing" in helps["--only-runtime"]
    assert "Implies --only-runtime" in helps["--apply-runtime"]


# ------------------------------------------------- 43.6 one tofu process at a time

def test_the_tofu_lock_refuses_a_second_holder_and_releases_on_any_exit(tmp_path):
    """Stage 64 item 2: the wrapper script became `cs-image-system --locked`;
    the lock's shape, the message and exit 75 are unchanged (the command's
    own tests are in tests/test_v2_release_whole.py)."""
    from cs_image_system.base import tofu_lock
    assert not (REPO / "scripts" / "with-tofu-lock").exists()
    cache = tmp_path / "cache"
    env = {"TF_PLUGIN_CACHE_DIR": str(cache)}
    release = tofu_lock.acquire(env)
    assert (cache / ".lock" / "pid").is_file()                               # held while the command runs
    release()
    assert not (cache / ".lock").exists()                                    # released after it
    (cache / ".lock").mkdir()
    (cache / ".lock" / "pid").write_text("12345\n")
    with pytest.raises(tofu_lock.LockHeld) as e:
        tofu_lock.acquire(env)
    assert e.value.holder == "12345" and "one tofu process at a time" in str(e.value) and tofu_lock.EX_TEMPFAIL == 75
    assert (cache / ".lock").exists()                                        # another holder's lock is never removed
