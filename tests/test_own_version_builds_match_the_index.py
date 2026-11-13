# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A package whose version the release does not move is fresh on the index or held there as this tree's build.

scripts/own-versions-current, against a fake index (the JSON API's page for
one version, or a 404) and a fake build (files written into the temporary
directory the script hands it): a version the index does not hold goes up
fresh and is never built; the index holding exactly the built files, name for
name and byte for byte, passes; a file that differs, or one held on one side
only, is an unbumped change (exit 1) whose lines name the package, the
version, the index and the manifest to bump; an index that cannot be asked,
a page that is not the JSON API or a failed build is exit 2. The members are
read from the root's bump exclusions, the private ones skipped, and the
index's JSON API from its ``[[tool.uv.index]]`` entry. No network, no build.
"""
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tomllib
import urllib.error
from collections.abc import Callable
from email.message import Message
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "own-versions-current"
SDIST, WHEEL = "x_own-0.2.0.tar.gz", "x_own-0.2.0-py3-none-any.whl"
BUILT = {SDIST: b"sdist bytes", WHEEL: b"wheel bytes"}

ROOT_PYPROJECT = """[project]
name = "x"
version = "0.1.0"

[[tool.uv.index]]
name = "testpypi"
url = "https://test.pypi.org/simple/"
publish-url = "https://test.pypi.org/legacy/"

[[tool.uv.index]]
name = "pypi"
url = "https://pypi.org/simple/"
publish-url = "https://upload.pypi.org/legacy/"

[[tool.bumpversion.files]]
glob = "packages/*/pyproject.toml"
glob_exclude = ["packages/own/pyproject.toml", "packages/private/pyproject.toml"]
search = "version = \\"{current_version}\\""

[[tool.bumpversion.files]]
glob = "packages/*/pyproject.toml"
glob_exclude = ["packages/own/pyproject.toml"]
search = "=={current_version}\\""
"""


def _load():
    loader = importlib.machinery.SourceFileLoader("own_versions_current", str(SCRIPT))
    spec = importlib.util.spec_from_loader("own_versions_current", loader)
    assert spec is not None
    m = importlib.util.module_from_spec(spec)
    sys.modules["own_versions_current"] = m          # the dataclasses resolve their annotations through the module
    loader.exec_module(m)
    return m


S = _load()


def _member(root: Path, folder: str, name: str, version: str, *, private: bool = False, readme: bool = False) -> None:
    (root / "packages" / folder).mkdir(parents=True)
    classifiers = '\nclassifiers = ["Private :: Do Not Upload"]' if private else ""
    (root / "packages" / folder / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "{version}"{classifiers}\n')
    if readme:
        (root / "packages" / folder / "README.md").write_text(f"# {name}\n\n### Version\n\nIts own.\n")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A workspace whose bump leaves two members alone -- one published (x-own, with a README that
    defines its bumps), one private -- and moves a third (x-lockstep)."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text(ROOT_PYPROJECT)
    _member(root, "own", "x-own", "0.2.0", readme=True)
    _member(root, "private", "x-private", "0.3.0", private=True)
    _member(root, "lockstep", "x-lockstep", "0.1.0")
    return root


def _page(files: dict[str, bytes]) -> bytes:
    """The JSON API's page for one version: each file's name and sha256 under ``urls``."""
    return json.dumps({"info": {"version": "0.2.0"}, "urls": [
        {"filename": n, "digests": {"sha256": hashlib.sha256(b).hexdigest()}} for n, b in files.items()]}).encode()


class FakeIndex:
    """Answers the JSON API from a page (None: a 404), or raises, and records the urls asked."""

    def __init__(self, page: bytes | None = None, error: Exception | None = None):
        self.page, self.error, self.asked = page, error, []

    def __call__(self, url: str) -> bytes | None:
        self.asked.append(url)
        if self.error is not None:
            raise self.error
        return self.page


class FakeBuild:
    """Writes the planned files (and uv's .gitignore) into the directory the script hands it."""

    def __init__(self, files: dict[str, bytes] | None = None, error: Exception | None = None):
        self.files, self.error, self.built = files if files is not None else BUILT, error, []

    def __call__(self, root: Path, name: str, out: Path) -> dict[str, str]:
        self.built.append(name)
        if self.error is not None:
            raise self.error
        (out / ".gitignore").write_text("*\n")
        for n, b in self.files.items():
            (out / n).write_bytes(b)
        return S.digests(out)


def _main(root: Path, target: str, index: Callable, build: Callable, capsys) -> tuple[int, str]:
    rc = S.main([target, "--root", str(root)], fetch=index, build=build)
    return rc, capsys.readouterr().out


# ------------------------------------------------------------ the members and the endpoint

def test_the_members_are_the_bumps_exclusions_that_are_published(root: Path):
    assert S.own_version_members(root) == [S.Member("x-own", "0.2.0", Path("packages/own/pyproject.toml"))]
    (root / "packages" / "own" / "pyproject.toml").write_text('[project]\nname = "x-own"\ndynamic = ["version"]\n')
    with pytest.raises(S.Unasked):
        S.own_version_members(root)


def test_this_repository_compares_the_contract_alone_at_its_own_version():
    manifest = REPO / "packages" / "contract" / "pyproject.toml"
    version = tomllib.loads(manifest.read_text())["project"]["version"]
    assert S.own_version_members(REPO) == [S.Member("cs-image-system-contract", version,
                                                    Path("packages/contract/pyproject.toml"))]
    assert S.json_api(REPO, "pypi") == "https://pypi.org/pypi"
    assert S.json_api(REPO, "testpypi") == "https://test.pypi.org/pypi"


def test_the_json_api_comes_from_the_index_entry(root: Path):
    assert S.json_api(root, "testpypi") == "https://test.pypi.org/pypi"
    with pytest.raises(S.Unasked):
        S.json_api(root, "gitlab")
    (root / "pyproject.toml").write_text('[[tool.uv.index]]\nname = "pypi"\nurl = "https://index.invalid/flat/"\n')
    with pytest.raises(S.Unasked):
        S.json_api(root, "pypi")


# ------------------------------------------------------------------ the outcomes

@pytest.mark.parametrize(("target", "url"), [("test", "https://test.pypi.org/pypi/x-own/0.2.0/json"),
                                             ("pypi", "https://pypi.org/pypi/x-own/0.2.0/json")])
def test_a_version_the_index_does_not_hold_goes_up_fresh_unbuilt(root: Path, capsys, target: str, url: str):
    index, build = FakeIndex(None), FakeBuild()
    rc, out = _main(root, target, index, build, capsys)
    assert rc == S.CURRENT and index.asked == [url] and build.built == []      # the private member is never asked
    assert out.startswith(S.PREFIX) and "x-own 0.2.0" in out and len(out.splitlines()) == 1


def test_the_index_holding_this_trees_build_file_for_file_passes(root: Path, capsys):
    build = FakeBuild()
    rc, out = _main(root, "pypi", FakeIndex(_page(BUILT)), build, capsys)
    assert rc == S.CURRENT and build.built == ["x-own"]
    assert SDIST in out and WHEEL in out and ".gitignore" not in out and len(out.splitlines()) == 1


def test_a_file_that_differs_is_an_unbumped_change_naming_what_to_bump(root: Path, capsys):
    rc, out = _main(root, "pypi", FakeIndex(_page({SDIST: b"sdist bytes", WHEEL: b"older wheel"})), FakeBuild(),
                    capsys)
    assert rc == S.CHANGED
    first, remedy = out.splitlines()
    assert first.startswith(S.PREFIX) and "x-own 0.2.0" in first and " pypi " in first
    assert WHEEL in first and SDIST not in first
    assert "packages/own/pyproject.toml" in remedy and "packages/own/README.md" in remedy


@pytest.mark.parametrize("held", [{SDIST: b"sdist bytes"},                                   # a file we built is not held
                                  {**BUILT, "x_own-0.2.0-py3-none-macosx_11_0_arm64.whl": b"w"}])  # the index holds one more
def test_a_file_on_one_side_only_is_an_unbumped_change(root: Path, capsys, held: dict[str, bytes]):
    rc, out = _main(root, "test", FakeIndex(_page(held)), FakeBuild(), capsys)
    assert rc == S.CHANGED and "testpypi" in out and len(out.splitlines()) == 2


def test_the_comparison_is_name_for_name_and_byte_for_byte():
    built = {"a.tar.gz": "1", "a.whl": "2", "b.whl": "3"}
    verdict = S.compare(built, {"a.tar.gz": "1", "a.whl": "9", "c.whl": "4"})
    assert (verdict.differ, verdict.index_only, verdict.built_only) == (("a.whl",), ("c.whl",), ("b.whl",))
    assert not verdict.current and S.compare(built, dict(built)).current


# ------------------------------------------------------------ nothing is guessed

def test_an_index_that_cannot_be_asked_or_a_page_that_is_not_the_api_is_exit_2(root: Path, capsys):
    build = FakeBuild()
    rc, _ = _main(root, "pypi", FakeIndex(error=S.Unasked("503")), build, capsys)
    assert rc == S.UNASKED and build.built == []
    rc, _ = _main(root, "pypi", FakeIndex(b"<html>maintenance</html>"), build, capsys)
    assert rc == S.UNASKED and build.built == []
    rc, _ = _main(root, "pypi", FakeIndex(_page(BUILT)), FakeBuild(error=S.Unasked("no backend")), capsys)
    assert rc == S.UNASKED
    rc, _ = _main(root, "gitlab", FakeIndex(None), build, capsys)
    assert rc == S.UNASKED


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://index.invalid/x", code, "x", Message(), io.BytesIO(b""))


def test_the_fetch_reads_a_404_as_not_held_and_anything_else_as_unasked(monkeypatch):
    answers: list[Exception] = [_http_error(404), _http_error(503), urllib.error.URLError("no route")]

    def urlopen(request, timeout):
        raise answers.pop(0)

    monkeypatch.setattr(S.urllib.request, "urlopen", urlopen)
    assert S.fetch("https://index.invalid/pypi/x/1/json") is None
    for _ in range(2):
        with pytest.raises(S.Unasked):
            S.fetch("https://index.invalid/pypi/x/1/json")


def test_a_change_outranks_an_index_that_could_not_be_asked(root: Path, capsys):
    _member(root, "own2", "x-own2", "0.5.0")
    config = (root / "pyproject.toml").read_text().replace('"packages/private/pyproject.toml"]',
                                                           '"packages/private/pyproject.toml", "packages/own2/pyproject.toml"]')
    (root / "pyproject.toml").write_text(config)

    def index(url: str) -> bytes | None:
        if "x-own2" in url:
            raise S.Unasked("503")
        return _page({SDIST: b"other", WHEEL: b"wheel bytes"})

    rc, out = _main(root, "pypi", index, FakeBuild(), capsys)
    assert rc == S.CHANGED and "x-own2 0.5.0" in out and "x-own 0.2.0" in out


def test_a_workspace_with_no_own_version_package_has_nothing_to_compare(root: Path, capsys):
    (root / "pyproject.toml").write_text(ROOT_PYPROJECT.replace("glob_exclude", "unused"))
    index = FakeIndex(None)
    rc, out = _main(root, "pypi", index, FakeBuild(), capsys)
    assert rc == S.CURRENT and index.asked == [] and len(out.splitlines()) == 1


def test_the_script_runs_by_name_and_a_workspace_it_cannot_read_is_exit_2(tmp_path: Path):
    assert os.access(SCRIPT, os.X_OK)
    done = subprocess.run([sys.executable, str(SCRIPT), "pypi", "--root", str(tmp_path)], capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == S.UNASKED and done.stdout.startswith(S.PREFIX)
