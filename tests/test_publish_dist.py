# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""scripts/publish-dist says what a release uploads, and uploads nothing.

On a workspace of five projects, one of them private, and on this repository: the order
(dependencies first, the root project last), a private project left out, a
version of a project's own, each project's sdist before its wheel, a missing
file named. The upload itself is the publish workflow's, by trusted
publishing: nothing here can send a file to an index.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "publish-dist"
VERSION = "0.1.1"


def _script():
    loader = importlib.machinery.SourceFileLoader("publish_dist", str(SCRIPT))
    spec = importlib.util.spec_from_loader("publish_dist", loader)
    assert spec is not None
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


@pytest.fixture
def world(tmp_path: Path) -> Path:
    """A workspace of five projects -- base (at a version of its own); a needs base; b needs base and
    a; a private one; the root needs the public three -- with the public ones' sdists and wheels built."""
    root = tmp_path / "repo"
    projects = {"cs-image-system-base": [], "cs-image-system-a": ["cs-image-system-base==0.9.0"],
                "cs-image-system-b": ["cs-image-system-a==0.1.1", "cs-image-system-base>=0.9"]}
    for name, deps in projects.items():
        d = root / "packages" / name.removeprefix("cs-image-system-")
        d.mkdir(parents=True)
        own = 'version = "0.9.0"\n' if name == "cs-image-system-base" else ""
        (d / "pyproject.toml").write_text(f'[project]\nname = "{name}"\n{own}dependencies = {json.dumps(deps)}\n')
    private = root / "packages" / "private"
    private.mkdir()
    (private / "pyproject.toml").write_text('[project]\nname = "cs-image-system-private"\n'
                                            'classifiers = ["Private :: Do Not Upload"]\n'
                                            'dependencies = ["cs-image-system-b==0.1.1"]\n')
    (root / "pyproject.toml").write_text(f"""[project]
name = "cs-image-system"
dependencies = {json.dumps([f"{n}=={VERSION}" for n in projects] + ["pydantic>=2"])}
""")
    dist = root / "dist"
    dist.mkdir()
    for name in ["cs-image-system", *projects]:
        stem = f"{name.replace('-', '_')}-{'0.9.0' if name == 'cs-image-system-base' else VERSION}"
        (dist / f"{stem}.tar.gz").write_bytes(b"s")
        (dist / f"{stem}-py3-none-any.whl").write_bytes(b"w")
    return root


def test_the_workspace_order_comes_from_the_dependencies(world: Path):
    m = _script()
    assert m.upload_order(world) == ["cs-image-system-base", "cs-image-system-a", "cs-image-system-b", "cs-image-system"]
    assert m.upload_order(REPO)[-1] == "cs-image-system"
    assert m.upload_order(REPO).index("cs-image-system-base") < m.upload_order(REPO).index("cs-image-system-system")


def test_a_private_project_is_never_in_the_upload(world: Path):
    m = _script()
    assert "cs-image-system-private" not in m.upload_order(world)
    assert world / "packages" / "private" / "pyproject.toml" not in m.published_pyprojects(world)


def test_a_project_with_a_version_of_its_own_is_looked_for_under_it(world: Path):
    m = _script()
    assert m.project_versions(world) == {"cs-image-system-base": "0.9.0"}
    files = m.files_of(world / "dist", "cs-image-system-base", m.project_versions(world)["cs-image-system-base"])
    assert [f.name for f in files] == ["cs_image_system_base-0.9.0.tar.gz", "cs_image_system_base-0.9.0-py3-none-any.whl"]


def test_each_projects_sdist_comes_before_its_wheel_and_a_missing_file_is_named(world: Path):
    m = _script()
    for project in m.upload_order(world):
        files = m.files_of(world / "dist", project, m.project_versions(world).get(project, VERSION))
        assert len(files) == 2 and files[0].name.endswith(".tar.gz") and files[1].name.endswith(".whl")
    with pytest.raises(FileNotFoundError, match="cs-image-system-a 9.9.9"):
        m.files_of(world / "dist", "cs-image-system-a", "9.9.9")


def test_nothing_here_can_send_a_file_to_an_index():
    """The safety this file owes (Constitution III): until 1.0 nothing reaches PyPI, and the one upload is
    the publish workflow's, by trusted publishing. So this file starts no process, reads no token and has
    no entry point to run."""
    m = _script()
    text = SCRIPT.read_text()
    assert not hasattr(m, "main") and "__main__" not in text
    for gone in ("subprocess", "os.environ", "UV_PUBLISH_TOKEN", "publish-url"):
        assert gone not in text, gone
