# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 64: the release is the whole system.

Item 1: the release carries the three starter configuration repositories
(the source is ``docs/examples/``; the build hook ships them inside the
system package) and ``cs-image-system init-config`` writes one out -- the
whole tree into an empty destination, only the release-owned parts into an
existing one -- with ``.csis-version`` pinned to the running release.
"""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cs_image_system.system import starters
from cs_image_system.system.cli import app
from v2_support import reset_singletons

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "docs" / "examples"


def _files(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and ".DS_Store" not in p.name}


def _invoke(*args: str):
    return CliRunner().invoke(app, ["init-config", *args])


# ------------------------------------------------------------ the starters

def test_the_release_carries_the_three_starters_and_the_source_is_docs_examples():
    root = starters.starters_root()
    assert sorted(starters.STARTERS) == ["complete", "standard-aws", "standard-gce"]
    for name in starters.STARTERS:
        assert (root / name / "cfg" / "_config.yml").is_file(), name
        # what the package resolves is byte for byte the source under docs/examples
        assert _files(root / name) == _files(EXAMPLES / name), name
    assert starters.release_version() == (REPO / "packages" / "system" / "pyproject.toml").read_text().split(
        'version = "', 1)[1].split('"', 1)[0]


def test_the_release_owned_parts_are_the_whole_repository_minus_the_teams_yaml():
    owned = starters.release_owned_paths(EXAMPLES / "standard-aws")
    for rel in ("Justfile", ".gitignore", ".githooks/pre-commit", ".github/workflows/ci.yml",
                "tfmodules/aws_instance/main.tf"):
        assert rel in owned, rel
    assert not any(p.startswith("scripts/") for p in owned)          # item 2: the helpers are commands
    assert not any(p.startswith(("cfg/", "groups/", "images/", "instances/", "storages/")) for p in owned)
    assert "README.md" not in owned and "scripts/mod_image.sh" not in starters.release_owned_paths(EXAMPLES / "complete")


def test_the_whole_system_package_exposes_the_command_to_uv_tool_install():
    """`uv tool install cs-image-system` exposes only the requested package's
    executables (the reference configuration's first CI run ended with
    "Failed to install entrypoints"): the metadata-only whole-system package
    declares the same console script the system package does."""
    import tomllib
    root = tomllib.loads((REPO / "pyproject.toml").read_text())
    system = tomllib.loads((REPO / "packages" / "system" / "pyproject.toml").read_text())
    assert root["project"]["scripts"]["cs-image-system"] == system["project"]["scripts"]["cs-image-system"] \
        == "cs_image_system.system.cli:app"


# ------------------------------------------------------------ init-config

@pytest.mark.parametrize("name", starters.STARTERS)
def test_init_config_writes_the_whole_starter_into_an_empty_destination(tmp_path, name):
    dest = tmp_path / "team-config"
    result = _invoke(str(dest), "--from", name)
    assert result.exit_code == 0, result.output
    written = _files(dest)
    expected = _files(EXAMPLES / name)
    assert written.pop(".csis-version") == starters.release_version().encode() + b"\n"
    assert written == expected, name
    assert (dest / ".githooks" / "pre-commit").stat().st_mode & stat.S_IXUSR     # the mode travelled
    assert "module_source_base: tfmodules" in (dest / "cfg" / "_config.yml").read_text()
    assert f"the whole tree of {name}" in result.output and "next: git init, just init" in result.output


def test_init_config_takes_an_empty_directory_too_and_defaults_to_standard_aws(tmp_path):
    dest = tmp_path / "empty"
    dest.mkdir()
    result = _invoke(str(dest))
    assert result.exit_code == 0, result.output
    assert (dest / "cfg" / "_config.yml").read_bytes() == (EXAMPLES / "standard-aws" / "cfg" / "_config.yml").read_bytes()


def test_init_config_on_an_existing_tree_writes_only_the_release_owned_parts(tmp_path):
    dest = tmp_path / "existing"
    (dest / "cfg").mkdir(parents=True)
    (dest / "cfg" / "_config.yml").write_text("config: {}\n")
    (dest / "groups").mkdir()
    (dest / "groups" / "users.yaml").write_text("users: []\n")
    result = _invoke(str(dest))
    assert result.exit_code == 0, result.output
    assert "the release-owned parts of standard-aws" in result.output
    assert (dest / "cfg" / "_config.yml").read_text() == "config: {}\n"      # the team's YAML is untouched
    assert (dest / "groups" / "users.yaml").read_text() == "users: []\n"
    assert not (dest / "images").exists() and not (dest / "README.md").exists()
    for rel in starters.release_owned_paths(EXAMPLES / "standard-aws"):
        assert (dest / rel).read_bytes() == (EXAMPLES / "standard-aws" / rel).read_bytes(), rel
    assert (dest / ".csis-version").read_text() == starters.release_version() + "\n"
    # a second run changes nothing and says so
    again = _invoke(str(dest))
    assert again.exit_code == 0 and "0 written" in again.output, again.output


def test_init_config_refuses_a_release_owned_file_that_differs_unless_forced(tmp_path):
    dest = tmp_path / "existing"
    (dest / "cfg").mkdir(parents=True)
    (dest / "cfg" / "_config.yml").write_text("config: {}\n")
    (dest / "Justfile").write_text("# a team's own recipes\n")
    (dest / ".csis-version").write_text("0.0.0\n")
    result = _invoke(str(dest))
    assert result.exit_code == 1, result.output
    assert "REFUSED Justfile" in result.output and "REFUSED .csis-version" in result.output
    assert (dest / "Justfile").read_text() == "# a team's own recipes\n"          # left alone
    assert (dest / "tfmodules" / "aws_instance" / "main.tf").is_file()          # the rest was written
    forced = _invoke(str(dest), "--force")
    assert forced.exit_code == 0, forced.output
    assert (dest / "Justfile").read_bytes() == (EXAMPLES / "standard-aws" / "Justfile").read_bytes()
    assert (dest / ".csis-version").read_text() == starters.release_version() + "\n"


def test_init_config_refuses_an_unknown_starter_and_a_file_destination(tmp_path):
    result = _invoke(str(tmp_path / "x"), "--from", "nope")
    assert result.exit_code == 2 and "no starter named 'nope'" in result.output and "standard-gce" in result.output
    f = tmp_path / "a-file"
    f.write_text("x")
    result = _invoke(str(f))
    assert result.exit_code == 2 and "is not a directory" in result.output


def test_init_config_loads_no_configuration(monkeypatch, tmp_path):
    """It runs where there is nothing to load yet: no identity, no session,
    no plugin -- from any working directory."""
    monkeypatch.delenv("CSIS_CONFIG_IDENTITY", raising=False)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["--root-dir", str(tmp_path / "nowhere"), "init-config", "team"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "team" / "Justfile").is_file()
    assert os.getcwd() == str(tmp_path)


# ================================================================ item 2
# The helper scripts became commands: `--locked` (with-tofu-lock), `config-drift`
# and `runtime-unchanged` (normalise-emission and the two recipes that used
# it), `workload token` (opa-workload-token). The starter Justfile calls the
# CLI alone and carries no scripts.

def test_the_three_helper_scripts_are_gone_from_the_repository_and_the_starters():
    for rel in ("scripts/with-tofu-lock", "scripts/opa-workload-token", "scripts/normalise-emission"):
        assert not (REPO / rel).exists(), rel
        for name in starters.STARTERS:
            assert not (EXAMPLES / name / rel).exists(), f"{name}/{rel}"
    for name in starters.STARTERS:
        just = (EXAMPLES / name / "Justfile").read_text()
        assert "scripts/" not in just, f"{name}: the starter Justfile must call the CLI alone"
        assert "--locked" in just and "config-drift" in just and "workload token" in just and "runtime-unchanged" in just


# --------------------------------------------------------------- --locked

def _locked(monkeypatch, tmp_path, *args: str, cache: Path | None = None) -> tuple:
    lock_cache: Path = cache if cache is not None else tmp_path / "cache"
    monkeypatch.setenv("TF_PLUGIN_CACHE_DIR", str(lock_cache))
    return CliRunner().invoke(app, ["--locked", *args]), lock_cache


def test_locked_holds_the_lock_for_the_command_and_releases_it_however_it_ends(monkeypatch, tmp_path):
    from cs_image_system.system import starters as st
    seen: dict[str, bool] = {}
    real = st.init_config

    def spy(*a, **k):
        seen["held"] = (tmp_path / "cache" / ".lock" / "pid").is_file()
        return real(*a, **k)
    monkeypatch.setattr(st, "init_config", spy)
    result, cache = _locked(monkeypatch, tmp_path, "init-config", str(tmp_path / "t"))
    assert result.exit_code == 0, result.output
    assert seen["held"] is True                                  # held while the command ran
    assert not (cache / ".lock").exists()                        # released after it
    # released on failure too (an unknown starter exits 2)
    result, cache = _locked(monkeypatch, tmp_path, "init-config", str(tmp_path / "u"), "--from", "nope")
    assert result.exit_code == 2 and not (cache / ".lock").exists()


def test_locked_refuses_a_second_holder_with_exit_75_and_never_removes_its_lock(monkeypatch, tmp_path):
    cache = tmp_path / "cache"
    (cache / ".lock").mkdir(parents=True)
    (cache / ".lock" / "pid").write_text("12345\n")
    result, _ = _locked(monkeypatch, tmp_path, "init-config", str(tmp_path / "t"), cache=cache)
    assert result.exit_code == 75, result.output
    assert "pid 12345" in result.output and "one tofu process at a time" in result.output
    assert (cache / ".lock").exists() and not (tmp_path / "t").exists()


def test_locked_needs_the_cache_directory_variable(monkeypatch, tmp_path):
    monkeypatch.delenv("TF_PLUGIN_CACHE_DIR", raising=False)
    result = CliRunner().invoke(app, ["--locked", "init-config", str(tmp_path / "t")])
    assert result.exit_code == 2 and "TF_PLUGIN_CACHE_DIR is not set" in result.output


def test_the_lock_module_keeps_the_shape_the_script_had(tmp_path):
    from cs_image_system.base import tofu_lock
    env = {"TF_PLUGIN_CACHE_DIR": str(tmp_path / "c")}
    release = tofu_lock.acquire(env)
    assert (tmp_path / "c" / ".lock" / "pid").read_text().strip() == str(os.getpid())
    with pytest.raises(tofu_lock.LockHeld) as e:
        tofu_lock.acquire(env)
    assert e.value.holder == str(os.getpid())
    release()
    assert not (tmp_path / "c" / ".lock").exists()
    assert tofu_lock.EX_TEMPFAIL == 75
    with pytest.raises(tofu_lock.NoCacheDir):
        tofu_lock.acquire({})


# ------------------------------------------------------- the normaliser

def test_normalise_emission_removes_residue_and_placeholders_run_ids_and_stamps(tmp_path):
    from cs_image_system.base.commands.emission import normalise_emission
    root = tmp_path / "generated"
    (root / "instance-image" / "b" / ".terraform").mkdir(parents=True)
    (root / "instance-image" / "b" / ".terraform.lock.hcl").write_text("x")
    (root / "instance-image" / "b" / "tfplan").write_text("x")
    (root / "release" / "release").mkdir(parents=True)
    (root / "retention" / "retention").mkdir(parents=True)
    for name in ("run-summary.json", "state-report.json", "manifest.json"):
        (root / name).write_text("{}")
    (root / "base-image" / "temp_assets").mkdir(parents=True)
    keep = root / "instance-image" / "b" / "main.tf"
    keep.write_text('run = "2026_09_26t10_38_27_569578"\nname = "img-20260926_103827"\nalso = "img-20260926-103827"\n')
    normalise_emission(root)
    assert not (root / "instance-image" / "b" / ".terraform").exists()
    assert not (root / "instance-image" / "b" / ".terraform.lock.hcl").exists()
    assert not (root / "instance-image" / "b" / "tfplan").exists()
    assert not (root / "release" / "release").exists() and (root / "release").is_dir()
    assert not (root / "retention" / "retention").exists()
    assert not (root / "base-image" / "temp_assets").exists()
    for name in ("run-summary.json", "state-report.json", "manifest.json"):
        assert not (root / name).exists(), name
    assert keep.read_text() == 'run = "<RUN>"\nname = "img-<STAMP>"\nalso = "img-<STAMP>"\n'


def test_diff_trees_names_what_differs_and_nothing_when_equal(tmp_path):
    from cs_image_system.base.commands.emission import diff_trees
    a, b = tmp_path / "a", tmp_path / "b"
    for r in (a, b):
        (r / "d").mkdir(parents=True)
        (r / "d" / "same.tf").write_text("x = 1\n")
    assert diff_trees(a, b) == []
    (a / "d" / "only-a.tf").write_text("a\n")
    (b / "d" / "same.tf").write_text("x = 2\n")
    (b / "new.tf").write_text("n\n")
    lines = diff_trees(a, b)
    assert any("Only in a/d: only-a.tf" in ln for ln in lines) and any("Only in b: new.tf" in ln for ln in lines)
    assert "diff d/same.tf" in lines and any(ln.startswith("-x = 1") for ln in lines) and any(ln.startswith("+x = 2") for ln in lines)


# ----------------------------------------------------------- config-drift

def _git(root: Path, *args: str) -> str:
    import subprocess
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


def _generated_tree(tmp_path, monkeypatch):
    """A fixture copy with a recorded dry run committed under generated/."""
    from v2_support import V2Run
    v2 = V2Run(tmp_path, monkeypatch)
    assert v2.run("all", apply=False).ok
    v2.restore_cwd()
    root = v2.config_root
    _git(root, "init", "-q", "-b", "develop")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "recorded")
    return v2


def _copy_of_committed(v2):
    """A stand-in dry run for the test: the copy gets the committed emission
    (the real command runs `run --all` in a process of its own)."""
    import shutil
    def dry_run(copy: Path) -> None:
        shutil.copytree(v2.generated, copy / "generated")
    return dry_run


def test_config_drift_reads_current_then_behind_then_nothing_committed(tmp_path, monkeypatch):
    from cs_image_system.base.commands.emission import config_drift
    v2 = _generated_tree(tmp_path, monkeypatch)
    root = v2.config_root
    code, lines = config_drift(root, dry_run=_copy_of_committed(v2))
    assert code == 0 and "current with the configuration" in lines[0], lines
    # a declaration moved the emission: the committed tree is behind
    def moved(copy: Path) -> None:
        _copy_of_committed(v2)(copy)
        tf = next((copy / "generated").rglob("*.tf"))
        tf.write_text(tf.read_text() + "\n# a change\n")
    code, lines = config_drift(root, dry_run=moved)
    assert code == 1 and "BEHIND the configuration (1 files)" in lines[0] and any(ln.startswith("+# a change") for ln in lines), lines
    # run ids never count as drift: the copy's differ from the record's
    def restamped(copy: Path) -> None:
        _copy_of_committed(v2)(copy)
        for p in (copy / "generated").rglob("*.sh"):
            p.write_text(re.sub(r"[0-9]{4}_[0-9]{2}_[0-9]{2}t[0-9]{2}_[0-9]{2}_[0-9]{2}_[0-9]{6}",
                                "2030_01_01t00_00_00_000000", p.read_text()))
    code, lines = config_drift(root, dry_run=restamped)
    assert code == 0, lines
    # a failing dry run and a tree with nothing committed under generated/
    def failing(copy: Path) -> None:
        raise RuntimeError("boom")
    code, lines = config_drift(root, dry_run=failing)
    assert code == 2 and "the dry run FAILED: boom" in lines[0]
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "cfg").mkdir()
    (bare / "cfg" / "_config.yml").write_text("config: {}\n")
    _git(bare, "init", "-q")
    code, lines = config_drift(bare, dry_run=failing)
    assert code == 2 and "nothing is committed under generated/" in lines[0]


def test_config_drift_copies_a_relative_module_source_base_that_escapes_the_tree(tmp_path):
    """The reference configuration reached the system's modules at
    ../cs-image-system-3/tfmodules until stage 64 item 3; a copy for a dry run
    puts the modules at the same relative place beside it."""
    from cs_image_system.base.commands.emission import copy_tree_for_a_dry_run
    site = tmp_path / "site"
    (site / "cs-image-system-3" / "tfmodules" / "m").mkdir(parents=True)
    (site / "cs-image-system-3" / "tfmodules" / "m" / "main.tf").write_text("module\n")
    root = site / "cs-image-system-testconfig"
    (root / "cfg").mkdir(parents=True)
    (root / "cfg" / "_config.yml").write_text("config:\n  module_source_base: ../cs-image-system-3/tfmodules\n")
    (root / "generated").mkdir()
    (root / "generated" / "x").write_text("never copied\n")
    copy = copy_tree_for_a_dry_run(root, tmp_path / "work")
    assert copy.name == root.name and (copy / "cfg" / "_config.yml").is_file() and not (copy / "generated").exists()
    assert (copy / "../cs-image-system-3/tfmodules/m/main.tf").resolve().read_text() == "module\n"
    # a base inside the tree needs nothing beside the copy
    (root / "cfg" / "_config.yml").write_text("config:\n  module_source_base: tfmodules\n")
    copy2 = copy_tree_for_a_dry_run(root, tmp_path / "work2")
    assert copy2 == tmp_path / "work2" / root.name


def test_config_drift_is_a_command_that_loads_nothing(tmp_path, monkeypatch):
    """The dry run happens in a process of its own; this process needs no
    identity and no session, only the tree and its git history."""
    from cs_image_system.base.commands import emission
    v2 = _generated_tree(tmp_path, monkeypatch)
    monkeypatch.setattr(emission, "subprocess_dry_run", _copy_of_committed(v2))
    monkeypatch.delenv("CSIS_CONFIG_IDENTITY", raising=False)
    reset_singletons()
    result = CliRunner().invoke(app, ["--root-dir", str(v2.config_root), "config-drift"])
    assert result.exit_code == 0, result.output
    assert "current with the configuration" in result.output


# ------------------------------------------------------ runtime-unchanged

def test_runtime_unchanged_compares_one_runtimes_directories_across_records(tmp_path, monkeypatch):
    from cs_image_system.base.commands.emission import runtime_unchanged
    v2 = _generated_tree(tmp_path, monkeypatch)
    root = v2.config_root
    os.chdir(root)
    code, lines = runtime_unchanged("gcloud-east1", "HEAD")
    assert code == 0 and "unchanged since HEAD" in lines[0] and "instance-image/" in lines[0], lines
    # a change under the OTHER runtime's directories is not this runtime's
    aws_dir = next(p for p in (root / "generated" / "instance-image").iterdir() if p.is_dir() and "gce" not in p.name)
    (aws_dir / "extra.tf").write_text("# aws only\n")
    code, lines = runtime_unchanged("gcloud-east1", "HEAD")
    assert code == 0, lines
    gce_dir = next(p for p in (root / "generated" / "instance-image").iterdir() if p.is_dir() and "gce" in p.name)
    (gce_dir / "extra.tf").write_text("# gce\n")
    code, lines = runtime_unchanged("gcloud-east1", "HEAD")
    assert code == 1 and "CHANGED since HEAD (1 files)" in lines[0] and any("extra.tf" in ln for ln in lines), lines
    code, lines = runtime_unchanged("no-such-runtime", "HEAD")
    assert code == 2 and "no runtime named" in lines[0]
    v2.restore_cwd()


# -------------------------------------------------------- workload token

def _stub_minting(monkeypatch, *, rc=0, token="opa-token-value", verdict="ok\n"):
    from cs_image_system.base.commands import workload_token as wt
    jwt = "hdr." + __import__("base64").urlsafe_b64encode(
        b'{"iss":"https://token.actions.githubusercontent.com","repository":"o/r","sub":"repo:o/r:ref:refs/heads/main"}').decode().rstrip("=") + ".sig"
    monkeypatch.setattr(wt, "fetch_oidc_token", lambda url, bearer: jwt)
    calls: list = []
    def authenticate(names, presented):
        calls.append((names, presented))
        return rc, token, verdict
    monkeypatch.setattr(wt, "sft_workload_authenticate", authenticate)
    return jwt, calls


def _job_env(monkeypatch, **names):
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_URL", "https://runner.invalid/token")
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "bearer-value")
    for k, v in names.items():
        monkeypatch.setenv(k, v)


def test_workload_token_prints_the_token_alone_and_masks_both_on_stderr(monkeypatch):
    jwt, calls = _stub_minting(monkeypatch)
    _job_env(monkeypatch, OPA_WORKLOAD_CONNECTION="conn", OPA_WORKLOAD_ROLE="role", SFT_TEAM="team",
             OPA_ADDR="https://x.pam.okta.com")
    monkeypatch.delenv("CSIS_CONFIG_IDENTITY", raising=False)
    from cs_image_system.base.commands.workload_token import mint_token, WorkloadNames
    said: list[str] = []
    token = mint_token(WorkloadNames("conn", "role", "team", "https://x.pam.okta.com"), dict(os.environ),
                       say=said.append, fetch=lambda u, b: jwt,
                       authenticate=lambda n, j: (0, "opa-token-value\n", "verdict line\n"))
    assert token == "opa-token-value"
    assert said[0] == f"::add-mask::{jwt}" and "::add-mask::opa-token-value" in said
    assert any(ln == "claim repository: o/r" for ln in said) and "verdict line" in said
    # the command: the token is the ONLY thing on stdout, from a checkout with no configuration
    result = CliRunner().invoke(app, ["--root-dir", "/nowhere", "workload", "token"])
    assert result.exit_code == 0, result.output
    assert result.stdout == "opa-token-value"
    assert calls and calls[0][0].connection == "conn" and calls[0][1] == jwt
    assert "::add-mask::" in result.stderr and "opa-token-value" not in result.stdout.replace("opa-token-value", "", 1)


def test_workload_token_fills_missing_names_from_the_configuration(monkeypatch, tmp_path):
    from v2_support import copy_config, stub_environment
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)
    # the fixture's builder names no workload objects; this copy's does
    gb = root / "cfg" / "group-builders.yml"
    gb.write_text(gb.read_text().replace('    team: "nos-coastal-modeling-cloud-sandbox"\n',
                                         '    team: "nos-coastal-modeling-cloud-sandbox"\n'
                                         '    workload_connection: github-cs-image-system\n'
                                         '    workload_role: cs-image-system-ci\n', 1))
    jwt, calls = _stub_minting(monkeypatch)
    _job_env(monkeypatch)
    for v in ("OPA_WORKLOAD_CONNECTION", "OPA_WORKLOAD_ROLE", "SFT_TEAM", "OPA_ADDR"):
        monkeypatch.delenv(v, raising=False)
    reset_singletons()
    result = CliRunner().invoke(app, ["--root-dir", str(root), "workload", "token"])
    assert result.exit_code == 0, result.output
    names = calls[0][0]
    assert names.team == "nos-coastal-modeling-cloud-sandbox" and names.connection == "github-cs-image-system"
    assert names.role == "cs-image-system-ci" and "pam.okta.com" in names.api_host
    assert result.stdout == "opa-token-value"


def test_workload_token_refuses_outside_a_job_and_reports_a_refused_token(monkeypatch):
    for v in ("ACTIONS_ID_TOKEN_REQUEST_URL", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    _stub_minting(monkeypatch)
    monkeypatch.setenv("OPA_WORKLOAD_CONNECTION", "c"); monkeypatch.setenv("OPA_WORKLOAD_ROLE", "r")
    monkeypatch.setenv("SFT_TEAM", "t"); monkeypatch.setenv("OPA_ADDR", "https://x")
    result = CliRunner().invoke(app, ["workload", "token"])
    assert result.exit_code == 2 and "not a GitHub Actions job" in result.output
    _stub_minting(monkeypatch, rc=1, token="", verdict="the connection is a draft\n")
    _job_env(monkeypatch)
    result = CliRunner().invoke(app, ["workload", "token"])
    assert result.exit_code == 1 and result.stdout == "" and "exited 1" in result.stderr and "the connection is a draft" in result.stderr
    _stub_minting(monkeypatch, rc=0, token="", verdict="")
    result = CliRunner().invoke(app, ["workload", "token"])
    assert result.exit_code == 1 and "issued no token" in result.stderr
