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
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cs_image_system.system import starters
from cs_image_system.system.cli import app

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
                "tfmodules/aws_instance/main.tf", "scripts/with-tofu-lock"):
        assert rel in owned, rel
    assert not any(p.startswith(("cfg/", "groups/", "images/", "instances/", "storages/")) for p in owned)
    assert "README.md" not in owned and "scripts/mod_image.sh" not in starters.release_owned_paths(EXAMPLES / "complete")


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
    for rel in (".githooks/pre-commit", "scripts/with-tofu-lock"):
        assert (dest / rel).stat().st_mode & stat.S_IXUSR, rel        # the mode travelled
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
