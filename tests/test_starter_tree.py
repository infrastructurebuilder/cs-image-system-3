# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 66: a template repository's tree is its starter and three generated
changes, nothing else.

scripts/starter-tree over every starter: the files are the rendered starter
(the skeleton under the overlay, every one of them a tracked file of this
repository), the installed plugins' terraform modules with their stamps, and
`.csis-version`; every file is byte-identical except the README's generated
header and the Markdown links that leave the starter's tree, which point at
the system repository at the release's tag -- and every such link names a
path that exists here.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import posixpath
import re
import subprocess
from pathlib import Path

import pytest

from cs_image_system.base.modules import STAMP_FILE, installed_modules
from cs_image_system.system import starters
from cs_image_system.system.starter_links import rewrite_links

REPO = Path(__file__).resolve().parents[1]
VERSION = "0.1.2"


def _script():
    loader = importlib.machinery.SourceFileLoader("starter_tree", str(REPO / "scripts" / "starter-tree"))
    spec = importlib.util.spec_from_loader("starter_tree", loader)
    assert spec is not None
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


def _tracked() -> set[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "docs/examples"], capture_output=True, check=True).stdout
    return {p for p in out.decode().split("\0") if p}


@pytest.mark.parametrize("name", starters.STARTERS)
def test_the_tree_is_the_starter_and_three_generated_changes(tmp_path: Path, name: str):
    m = _script()
    assert name in m.starters()
    files = m.build(name, VERSION, tmp_path / "t")
    dest = tmp_path / "t"
    want = starters.render(name)
    tracked = _tracked()
    for rel in want:                        # every rendered file is a tracked file: the skeleton's or the overlay's
        assert f"docs/examples/_skeleton/{rel}" in tracked or f"docs/examples/{name}/{rel}" in tracked, rel
    modules = {rel: p.read_bytes() for rel, p in starters.installed_module_files("tfmodules").items()}
    stamps = {f"tfmodules/{module}/{STAMP_FILE}" for module in installed_modules()}
    assert set(files) == set(want) | set(modules) | stamps | {".csis-version"}
    assert (dest / ".csis-version").read_text() == f"{VERSION}\n"
    for rel, data in modules.items():
        assert (dest / rel).read_bytes() == data, rel
    for rel in stamps:
        assert (dest / rel).read_text().startswith("plugin: "), rel
    prefix = f"https://github.com/{m.SYSTEM_REPO}/"
    for rel, original in want.items():
        got = (dest / rel).read_bytes()
        if not rel.endswith(".md"):
            assert got == original, f"{rel} changed"
            continue
        text = got.decode()
        if rel == "README.md":
            assert text.startswith(m.HEADER_MARK)
            assert ".age-identity" in text.split("\n\n", 1)[0], "the header says to replace the TEST identity"
            text = text[len(m.header(name, VERSION)):]
        # what is left differs from the starter only in its rewritten links: every link that does
        # not point into the tree, and nothing else
        file_dir = posixpath.dirname(f"docs/examples/{name}/{rel}")
        assert text == rewrite_links(original.decode(), file_dir, f"docs/examples/{name}", VERSION), rel
        for target in re.findall(r"\]\(([^)\s]+)\)", original.decode()):
            inside = posixpath.normpath(posixpath.join(file_dir, target.split("#", 1)[0]))
            if not re.match(r"^[a-z][a-z0-9+.-]*:|^#", target) and not inside.startswith(f"docs/examples/{name}"):
                assert f"]({prefix}" in text and f"/v{VERSION}/{inside}" in text, f"{rel}: {target} not rewritten"
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if target.startswith(prefix):
                path = re.sub(r"^(blob|tree)/[^/]+/", "", target[len(prefix):]).split("#", 1)[0]
                assert (REPO / path).exists(), f"{rel}: {target} names no file here"
            elif not re.match(r"^[a-z][a-z0-9+.-]*:|^#", target):
                resolved = (dest / Path(rel).parent / target.split("#", 1)[0]).resolve()
                assert str(resolved).startswith(str(dest.resolve())), f"{rel}: {target} leaves the tree"


def test_the_template_repositories_are_named_after_the_starters():
    m = _script()
    assert [m.template_repo(n) for n in ("standard-aws", "complete")] == [
        "infrastructurebuilder/cs-image-system-starter-standard-aws",
        "infrastructurebuilder/cs-image-system-starter-complete"]


def test_a_destination_that_holds_files_is_refused(tmp_path: Path):
    (tmp_path / "x").write_text("x")
    with pytest.raises(SystemExit, match="is not empty"):
        _script().build("standard-aws", VERSION, tmp_path)
    with pytest.raises(SystemExit, match="no starter named"):
        _script().build("nonesuch", VERSION, tmp_path / "new")
