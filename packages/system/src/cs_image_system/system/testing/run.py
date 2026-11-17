# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The test kit's stubbed run.

A test that needs a whole run drives the real pipeline over a private copy
of a fixture configuration, with everything outside the process answered
by stubs:

* no tools: ``ExecutableModel.execute`` is journaled, never run, and the
  system's own in-process steps are journaled the same way;
* deterministic: the run's clock and ``USER`` are pinned, and the
  fixture's own test identity opens its encrypted values;
* no provider: this module names none and imports none. What stands in for
  a provider's calls to the outside world is a *stub function*, shipped by
  that provider's own package and handed in by the caller.

A stub function takes the test's ``monkeypatch`` and returns nothing.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import types
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast

# the system's CLI registers the real in-process runner at import; importing
# it here, before any test opens a patch window, means a test's teardown
# restores that runner and not ``None``
import cs_image_system.system.cli  # noqa: F401
from cs_image_system.base import encryption, os_types
from cs_image_system.base import lifecycles as lifecycles_module
from cs_image_system.base.models.executable import ExecutableModel
from cs_image_system.contract.constants import SYSTEM_CLI
from cs_image_system.engine import config_loader, in_process, loader, modules
from cs_image_system.engine.commands import run_lifecycles as _run_lifecycles
from cs_image_system.engine.commands import validate as _validate

FIXED_NOW = datetime(2026, 8, 26, 12, 0, 0)
FIXED_TIMESTAMP = "20260826_120000"          # FIXED_NOW in the fixtures' dateformat
FIXED_RUN_ID = "2026_08_26t12_00_00"         # iso_sanitized

#: the fixed timestamp of a record a copy starts with: a dry run never
#: rewrites such a record, so the copy's file is the test's input, not the
#: run's output
FIXED_CHECKED_AT = "2026-01-01T00:00:00+00:00"

#: the name of the test identity every fixture carries at its root
IDENTITY_FILE = ".age-identity"

#: A stub function: takes the test's ``monkeypatch``, replaces one
#: provider's (or one library's) calls to the outside world.
Stub = Callable[[Any], None]


class _FixedDT(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return FIXED_NOW


def copy_fixture(fixture: Path, tmp_path: Path, name: str = "config") -> Path:
    """A private copy of the fixture at ``fixture`` (without any generated
    output or meta-state), under ``tmp_path/name``; the copy's root is
    returned. The transient ``apply_*`` flags are normalised to false -- a
    live run's temporary flag flip must never leak into a test -- and so is
    a runtime's ``ephemeral: true``: a copy starts non-ephemeral, and a
    test that wants either sets it itself."""
    dst = tmp_path / name
    # A fixture carries no generated output and no meta-state (records of
    # live resources); the ignore list is the guard that keeps a copy so
    # should either ever be found in one.
    shutil.copytree(fixture, dst,
                    ignore=shutil.ignore_patterns("generated", "meta-state", ".git", ".DS_Store"))
    cfg = dst / "cfg" / "_config.yml"
    cfg.write_text(re.sub(r"^(  apply_\w+:) \S+.*$", r"\1 false", cfg.read_text(), flags=re.M))
    rb = dst / "cfg" / "runtime-builders.yml"
    if rb.is_file():
        rb.write_text(re.sub(r"^(\s+ephemeral:) true.*$", r"\1 false", rb.read_text(), flags=re.M))
    return dst


def module_path(name: str) -> Path:
    """The directory of one installed terraform module, inside the plugin
    that ships it (``installed_modules()[name].path``)."""
    return modules.installed_modules()[name].path


def modules_beside(config_root: Path) -> Path:
    """Every installed module written (and stamped) into
    ``<config_root>/../tfmodules``, where a fixture whose
    ``module_source_base`` is ``../tfmodules`` expects them; the directory
    is returned."""
    dest = config_root.parent / "tfmodules"
    report = modules.materialise_modules(dest)
    assert report.ok, "\n".join(report.lines())
    return dest


def modules_inside(config_root: Path) -> Path:
    """Every installed module written into the tree's own ``tfmodules``
    directory, where a starter's ``module_source_base`` (``tfmodules``)
    expects them; the directory is returned."""
    dest = config_root / "tfmodules"
    report = modules.materialise_modules(dest)
    assert report.ok, "\n".join(report.lines())
    return dest


def plain(value: Any, identity: Path) -> Any:
    """The plaintext of a fixture value that may be an ``ENC[age:...]``
    marker, opened with the test identity at ``identity`` -- for a test
    that addresses roster entries by name in the raw YAML."""
    if encryption.is_marker(value):
        return encryption.decrypt_marker(value, encryption._identities_for(str(identity)))
    return value


class BareRun:
    """A bare run context for a builder driven outside a run: the global
    ``config:`` map (backends off unless given), the declared state backends
    (none unless given) and ``plugin_state``, the slot per key a library
    keeps its per-run objects in, exactly as the core's context has them,
    plus ``dry_run`` and whatever else a test sets. Two holders are two
    runs: an object made on one is invisible to the other."""

    dry_run: bool = False

    def __init__(self, **attrs: Any) -> None:
        self.config: dict[str, Any] = attrs.pop("config", {})
        self.state_backends: dict[str, Any] = attrs.pop("state_backends", {})
        self._state: dict[str, Any] = {}
        for name, value in attrs.items():
            setattr(self, name, value)

    def plugin_state(self, key: str, factory: Callable[[], Any]) -> Any:
        if key not in self._state:
            self._state[key] = factory()
        return self._state[key]


def bare_run(**attrs: Any) -> BareRun:
    """See :class:`BareRun`."""
    return BareRun(**attrs)


def os_type_for_family(family: str | None) -> type:
    """The OS type that serves ``family`` among the INSTALLED plugins' types
    (a registry of the lookup's own): what a loaded run answers through
    ``ctx.services.images.os_type_for_family``, for a test that drives no
    run."""
    return os_types.os_type_for_family(family, loader.installed_registry())


def passing_session(real: Callable[..., tuple[int, str]]) -> Callable[..., tuple[int, str]]:
    """A stand-in for a runtime's ``run_session_command``, for a provider's
    stub function to install: it answers PASS for every assertion a
    post-bake test script carries, and hands any other script (an unmount,
    say) to ``real``, whose subprocess is what those tests fake."""
    def _run(self, name, script, timeout=300):
        idx = re.findall(r'CSIS_TEST (\d+) PASS', script)
        if not idx:
            return real(self, name, script, timeout)
        return 0, "".join(f"CSIS_TEST {i} PASS\n" for i in sorted(set(idx), key=int))
    return _run


def stub_core(monkeypatch, identity: Path, stubs: Sequence[Stub] = ()) -> list[str]:
    """Install the core's stubs and then each of ``stubs``; the command
    journal is returned. ``identity`` is the fixture's test identity file.

    The installed plugins are held to the contract ONCE, as shipped, before
    any hook is replaced: a stub's parameter names are the test's, not the
    plugin's (memoised: free after the first call)."""
    loader.discover_plugins()
    monkeypatch.setenv("USER", "testuser")
    # the fixture's TEST identity opens its encrypted values
    monkeypatch.setenv("CSIS_CONFIG_IDENTITY", str(identity))

    monkeypatch.setattr(config_loader, "datetime", _FixedDT)     # the loader's clock is the run's

    for stub in stubs:
        stub(monkeypatch)

    journal: list[str] = []

    def _fake_execute(self, *args, skips=False):
        cmd = [self.binary or self.name] + list(self.args or []) + list(args)
        journal.append(f"{self.working_directory}: {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ExecutableModel, "execute", _fake_execute)

    # The system's own steps (materialize, gate-plan, prune-attachments,
    # release --declared, ...) do not go through `execute`: the executor
    # runs them IN PROCESS over the loaded context through the seam the
    # system's CLI registers at import. They are journaled the same way
    # (the same line a spawned step would have produced), so a test reads
    # one journal; a test of the in-process path itself registers its own
    # runner after its run is constructed.

    def _fake_runner(ctx, args, working_directory):
        journal.append(f"{working_directory}: {SYSTEM_CLI} {' '.join(str(a) for a in args)}")
        return 0

    monkeypatch.setattr(in_process, "_RUNNER", _fake_runner)

    monkeypatch.setattr(_validate, "check_executables_exist_and_versions", lambda ctx: [])
    return journal


def load_context(config_root: Path, dry_run: bool = True, overlays: list[Path] | None = None,
                 undeclare: list[str] | None = None):
    """The loader's run context over ``config_root`` (plus any transient
    ``--overlay`` files and ``--undeclare`` specs). A new context per load,
    with a registry, an image-source catalog and a template resolver of its
    own: the returned one is THE context of the run the test drives, and
    nothing of an earlier load is left in the process to reset."""
    return config_loader.read_config_and_transform(cast(Any, types.SimpleNamespace(obj={})),
                                     config_root, False, dry_run=dry_run,
                                     overlays=list(overlays or []), undeclare=list(undeclare or []))


def cli_context(ctx) -> Any:
    """The typer context a console-script command reads the loaded context
    from (``typer_cntx.obj["ctx"]``), for calling a command
    function directly."""
    return cast(Any, types.SimpleNamespace(obj={"ctx": ctx}))


def drive_lifecycles(ctx, lifecycles: list[str] | str = "all", *, apply: bool = True, commit: bool = False,
                     state_query: bool = False, only: list[str] | None = None,
                     force_bake: list[str] | None = None):
    """``ctx`` is the context ``load_context`` returned (passed, never
    fetched). ``state_query`` is OFF here: the real hooks would reach the
    outside world. A test of the pre-run query stubs the hooks and passes
    ``state_query=True``."""
    names = [lifecycles] if isinstance(lifecycles, str) else lifecycles
    return _run_lifecycles.run_lifecycles(ctx, lifecycles_module.parse_lifecycles(names), apply=apply, commit=commit,
                          state_query=state_query, only=only, force_bake=force_bake)


class Run:
    """One prepared copy of a fixture and its loaded context; ``run()``
    drives lifecycles. ``fixture`` is the fixture configuration's root and
    ``stubs`` the stub functions of the providers it declares."""

    def __init__(self, tmp_path: Path, monkeypatch, *, fixture: Path, stubs: Sequence[Stub] = (),
                 dry_run: bool = True, config_root: Path | None = None,
                 overlays: list[Path] | None = None, undeclare: list[str] | None = None):
        self.journal = stub_core(monkeypatch, fixture / IDENTITY_FILE, stubs)
        self.config_root = config_root or copy_fixture(fixture, tmp_path)
        self._cwd = os.getcwd()
        self.ctx = load_context(self.config_root, dry_run=dry_run, overlays=overlays, undeclare=undeclare)
        self.generated = self.config_root / "generated"
        self.meta_state = self.config_root / "meta-state"

    def run(self, lifecycles: list[str] | str = "all", *, apply: bool = True, commit: bool = False,
            state_query: bool = False, only: list[str] | None = None,
            force_bake: list[str] | None = None):
        return drive_lifecycles(self.ctx, lifecycles, apply=apply, commit=commit, state_query=state_query,
                                only=only, force_bake=force_bake)

    def restore_cwd(self) -> None:
        os.chdir(self._cwd)


def tree(root: Path, *, ignore_parts: tuple[str, ...] = (".terraform", "temp_assets")) -> dict[str, str]:
    """``{relative path: text}`` for every file under root."""
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in ignore_parts for part in rel.parts):
            continue
        out[str(rel)] = p.read_text()
    return out


def command_lines(script_text: str) -> list[str]:
    """The executable lines of a runner script (no shebang/comments/set/cd)."""
    lines = []
    for line in script_text.splitlines():
        s = line.strip()
        if (not s or s.startswith("#") or s.startswith("set ") or s == 'cd "$(dirname "$0")"'
                or s.startswith("CSIS_ROOT=")):
            continue
        lines.append(s)
    return lines
