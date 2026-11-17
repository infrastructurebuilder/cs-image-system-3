# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""scripts/isolated-run decides strictly and installs only what is declared.

The script runs one package's tests in an environment that holds only that
package and what it declares. Held here, against a stubbed shell and wheels
the test writes: a run passes only when tests were collected, none was
skipped and none failed; a step that cannot start means the tests did not
run, which is a failure; and the distributions installed from this
repository's build are exactly those the requirement reaches through
declared dependencies, with the extras asked for.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest
from packaging.requirements import Requirement

REPO = Path(__file__).resolve().parents[1]


def _script() -> Any:
    loader = importlib.machinery.SourceFileLoader("isolated_run", str(REPO / "scripts" / "isolated-run"))
    spec = importlib.util.spec_from_loader("isolated_run", loader)
    assert spec is not None
    m = importlib.util.module_from_spec(spec)
    sys.modules["isolated_run"] = m          # its dataclasses look their module up by name
    loader.exec_module(m)
    return m


I = _script()


def _wheel(directory: Path, name: str, requires: list[str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stem = name.replace("-", "_")
    path = directory / f"{stem}-1.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{stem}-1.0.dist-info/METADATA",
                   "\n".join([f"Name: {name}", "Version: 1.0", *(f"Requires-Dist: {r}" for r in requires)]) + "\n")
    return path


def _junit(tests: int, skipped: int = 0, failures: int = 0, errors: int = 0) -> str:
    return (f'<testsuites><testsuite name="pytest" tests="{tests}" skipped="{skipped}" '
            f'failures="{failures}" errors="{errors}"/></testsuites>')


# ------------------------------------------------------------ the verdict

@pytest.mark.parametrize("counts, passes", [
    (I.Counts(collected=5, skipped=0, failed=0), True),
    (I.Counts(collected=0, skipped=0, failed=0), False),     # nothing collected
    (I.Counts(collected=5, skipped=1, failed=0), False),     # a skipped test did not run
    (I.Counts(collected=5, skipped=0, failed=1), False),
    (None, False),                                            # pytest never wrote a report
])
def test_a_run_passes_only_when_tests_ran_and_none_was_skipped_or_failed(counts, passes):
    assert I.verdict(counts)[0] is passes


def test_the_report_is_read_as_totals_and_an_error_counts_as_a_failure(tmp_path: Path):
    report = tmp_path / "junit.xml"
    assert I.read_counts(report) is None
    report.write_text(_junit(tests=7, skipped=2, failures=1, errors=1))
    assert I.read_counts(report) == I.Counts(collected=7, skipped=2, failed=2)


# ------------------------------------------------------------ what is installed

def test_the_closure_follows_declared_dependencies_and_the_extras_asked_for(tmp_path: Path):
    d = tmp_path / "wheels"
    _wheel(d, "pkg-plugin", ["pkg-kit==1.0", "thirdparty>=2", 'pkg-testkit[extra]==1.0 ; extra == "test"'])
    _wheel(d, "pkg-kit", ["pkg-contract>=1"])
    _wheel(d, "pkg-contract", [])
    _wheel(d, "pkg-testkit", ['pkg-engine==1.0', 'pytest>=8 ; extra == "extra"'])
    _wheel(d, "pkg-engine", ["pkg-kit==1.0"])
    _wheel(d, "pkg-other-plugin", ["pkg-kit==1.0"])            # built here, declared by nobody asked
    wheels = I.wheels_by_name(d)
    bare = I.closure(Requirement("pkg-plugin"), wheels)
    assert sorted(bare) == ["pkg-contract", "pkg-kit", "pkg-plugin"]
    with_tests = I.closure(Requirement("pkg-plugin[test]"), wheels)
    assert sorted(with_tests) == ["pkg-contract", "pkg-engine", "pkg-kit", "pkg-plugin", "pkg-testkit"]
    assert with_tests["pkg-testkit"] == {"", "extra"} and with_tests["pkg-plugin"] == {"", "test"}
    lines = I.install_lines(with_tests, wheels)
    assert all(" @ file://" in line for line in lines) and any(line.startswith("pkg-testkit[extra] @ ") for line in lines)


# ------------------------------------------------------------ the whole run, with a stubbed shell

class _Shell:
    """Answers each command by its first distinguishing words; writes the
    wheels on the build and the junit report on the pytest call."""

    def __init__(self, tmp_path: Path, *, junit: str | None, fail: str | None = None, stray: str | None = None):
        self.tmp_path, self.junit, self.fail, self.stray = tmp_path, junit, fail, stray
        self.calls: list[list[str]] = []

    def __call__(self, cmd, cwd):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        step = " ".join(cmd[:3])
        if self.fail and self.fail in " ".join(cmd):
            return I.Done(1, "it broke")
        if step.startswith("uv build --all-packages"):
            out = Path(cmd[cmd.index("--out-dir") + 1])
            _wheel(out, "cs-image-system-thing-plugin", ["cs-image-system-kit==1.0", "thirdparty>=1"])
            _wheel(out, "cs-image-system-kit", [])
        if step.startswith("uv pip list"):
            names = ["cs-image-system-thing-plugin", "cs-image-system-kit", "thirdparty", *([self.stray] if self.stray else [])]
            return I.Done(0, "\n".join(f"{n}==1.0" for n in names))
        if "pytest" in cmd and self.junit is not None:
            next(Path(c.split("=", 1)[1]) for c in cmd if c.startswith("--junitxml=")).write_text(self.junit)
        return I.Done(0, "")


def _run(tmp_path: Path, shell: _Shell) -> tuple[int, list[str]]:
    said: list[str] = []
    root = tmp_path / "pkg"
    root.mkdir(exist_ok=True)
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    rc = I.run("thing", "cs-image-system-thing-plugin", root, [], copy_outside=False, shell=shell, say=said.append,
               work=work)
    return rc, said


def test_a_clean_run_passes_and_installs_each_workspace_distribution_from_its_wheel(tmp_path: Path):
    shell = _Shell(tmp_path, junit=_junit(tests=4))
    rc, said = _run(tmp_path, shell)
    assert rc == 0 and "passed" in said[-1]
    install = next(c for c in shell.calls if c[:3] == ["uv", "pip", "install"])
    ours = [a for a in install if a.startswith("cs-image-system-")]
    assert len(ours) == 2 and all(" @ file://" in a for a in ours)          # by file: nothing of ours from an index
    pytest_call = next(c for c in shell.calls if "pytest" in c)
    assert "pythonpath" not in " ".join(pytest_call) and "-c" in pytest_call  # the package's own settings alone


@pytest.mark.parametrize("junit", [_junit(tests=0), _junit(tests=4, skipped=1), _junit(tests=4, failures=1), None])
def test_no_tests_a_skip_a_failure_or_no_report_each_fail_the_run(tmp_path: Path, junit):
    rc, said = _run(tmp_path, _Shell(tmp_path, junit=junit))
    assert rc == 1 and "FAILED" in said[-1]


@pytest.mark.parametrize("step", ["uv build", "uv venv", "uv pip install"])
def test_a_step_that_does_not_succeed_means_the_tests_did_not_run(tmp_path: Path, step: str):
    shell = _Shell(tmp_path, junit=_junit(tests=4), fail=step)
    rc, said = _run(tmp_path, shell)
    assert rc == 1 and "did not run" in said[-1]
    assert not any("pytest" in c for c in shell.calls)


def test_an_undeclared_distribution_of_this_repository_in_the_environment_fails_the_run(tmp_path: Path):
    shell = _Shell(tmp_path, junit=_junit(tests=4), stray="cs-image-system-neighbour-plugin")
    rc, said = _run(tmp_path, shell)
    assert rc == 1 and "cs-image-system-neighbour-plugin" in said[-1]
    assert not any("pytest" in c for c in shell.calls)


# ------------------------------------------------------------ the two ends of a provider's SDK range

def _sdk_wheels(directory: Path, built: str, spec: str = ">=0.2,<0.3") -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stem = "cs_image_system_base"
    kit = directory / f"{stem}-{built}-py3-none-any.whl"
    with zipfile.ZipFile(kit, "w") as z:
        z.writestr(f"{stem}-{built}.dist-info/METADATA", f"Name: cs-image-system-base\nVersion: {built}\n")
    _wheel(directory, "cs-image-system-thing-plugin", [f"cs-image-system-base{spec}", "thirdparty>=1"])
    return I.wheels_by_name(directory)


def _versions(*texts: str):
    from packaging.version import Version
    return lambda name: {Version(t) for t in texts}


@pytest.mark.parametrize("held, built, end, version, from_index", [
    ((), "0.2.0", "low", "0.2.0", False),                       # nothing published: the build, at both ends
    ((), "0.2.0", "high", "0.2.0", False),
    (("0.2.0", "0.2.1"), "0.2.2", "low", "0.2.0", True),        # the oldest published one in the range
    (("0.2.0", "0.2.1"), "0.2.2", "high", "0.2.2", False),      # the build is newer than anything published
    (("0.2.0", "0.2.1"), "0.2.1", "high", "0.2.1", True),       # the build's version is published: from the index
    (("0.1.10", "0.3.0"), "0.2.0", "low", "0.2.0", False),      # published versions outside the range do not count
])
def test_each_end_is_the_lowest_or_highest_version_in_the_range_and_says_where_it_comes_from(
        tmp_path: Path, held, built: str, end: str, version: str, from_index: bool):
    wheels = _sdk_wheels(tmp_path / "wheels", built)
    [choice] = I.sdk_choices(Requirement("cs-image-system-thing-plugin"), wheels, end, _versions(*held))
    assert (choice.name, str(choice.version), choice.from_index) == ("cs-image-system-base", version, from_index)
    assert (I.FROM_INDEX in choice.said()) is from_index and (I.FROM_BUILD in choice.said()) is not from_index


def test_a_range_that_neither_the_index_nor_the_build_satisfies_is_an_error(tmp_path: Path):
    wheels = _sdk_wheels(tmp_path / "wheels", "0.3.0")
    with pytest.raises(ValueError, match="cs-image-system-base"):
        I.sdk_choices(Requirement("cs-image-system-thing-plugin"), wheels, "high", _versions("0.1.10"))


def test_an_index_that_cannot_be_asked_fails_the_run_and_nothing_is_guessed(tmp_path: Path):
    def unasked(name: str):
        raise I.IndexUnasked(f"{name}: no route to the index")
    said: list[str] = []
    root = tmp_path / "pkg"
    root.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    shell = _Shell(tmp_path, junit=_junit(tests=4))
    real_build = shell.__call__

    def with_sdk(cmd, cwd):
        done = real_build(cmd, cwd)
        if " ".join(str(c) for c in cmd[:3]).startswith("uv build --all-packages"):
            _sdk_wheels(Path(cmd[cmd.index("--out-dir") + 1]), "0.2.0")
        return done
    rc = I.run("thing", "cs-image-system-thing-plugin", root, [], copy_outside=False, sdk_end="low",
               published=unasked, shell=with_sdk, say=said.append, work=work)
    assert rc == 1 and "did not run" in said[-1] and "no route to the index" in said[-1]
    assert not any("pytest" in c for c in shell.calls)
