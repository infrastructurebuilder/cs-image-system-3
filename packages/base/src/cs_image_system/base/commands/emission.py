# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Is the committed emission current? (stage 45; commands of the CLI since
stage 64 item 2, where ``scripts/normalise-emission`` and the two Justfile
recipes that used it became ``config-drift`` and ``runtime-unchanged``.)

``normalise_emission`` edits a COPY of an emitted tree so two runs of the
same configuration compare equal: tool residue and the run-local files are
removed; run ids and the run's date stamp in image names (the configured
dateformat ``%Y%m%d_%H%M%S``, or the hyphenated form -- an image that is DUE
for a bake carries the run's stamp until it is baked) become placeholders.
Nothing else legitimately differs: since stage 38 the emission names no
absolute path, so a machine's path appearing here IS drift.

``config_drift`` runs a headless dry ``run --all`` over a private copy of the
configuration and compares its ``generated/`` with the one committed at HEAD.
``runtime_unchanged`` compares one runtime's emission directories in the
working tree with the same paths at a ref, which is how CI knows a
declaration changed on a runtime it must never bake on.
"""
from __future__ import annotations

import difflib
import filecmp
import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Callable

import yaml

from ..constants import RUN_LOCAL_FILENAMES

log = logging.getLogger(__name__)

# names pruned wherever they are, and path suffixes pruned
RESIDUE_NAMES: tuple[str, ...] = (".terraform", ".terraform.lock.hcl", "tfplan", "temp_assets", *RUN_LOCAL_FILENAMES)
RESIDUE_SUFFIXES: tuple[str, ...] = ("release/release", "retention/retention")
RUN_ID = re.compile(rb"[0-9]{4}_[0-9]{2}_[0-9]{2}t[0-9]{2}_[0-9]{2}_[0-9]{2}_[0-9]{6}")
STAMP = re.compile(rb"[0-9]{8}[-_][0-9]{6}")
RUN_PLACEHOLDER = b"<RUN>"
STAMP_PLACEHOLDER = b"<STAMP>"

DryRun = Callable[[Path], None]


def normalise_emission(directory: Path) -> None:
    """Edit ``directory`` in place (see the module docstring)."""
    directory = Path(directory)
    for path in sorted(directory.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        rel = path.relative_to(directory).as_posix()
        if path.name in RESIDUE_NAMES or any(rel.endswith(s) for s in RESIDUE_SUFFIXES):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
    for path in sorted(directory.rglob("*")):
        if path.is_file() and not path.is_symlink():
            data = path.read_bytes()
            new = STAMP.sub(STAMP_PLACEHOLDER, RUN_ID.sub(RUN_PLACEHOLDER, data))
            if new != data:
                path.write_bytes(new)


def diff_trees(expected: Path, actual: Path, *, limit: int = 120) -> list[str]:
    """Lines describing how ``actual`` differs from ``expected``: files only
    on one side, and a unified diff per changed text file; empty when equal."""
    out: list[str] = []

    def walk(cmp: filecmp.dircmp, rel: str) -> None:
        for name in sorted(cmp.left_only):
            out.append(f"Only in {f'{expected.name}/{rel}'.rstrip('/')}: {name}")
        for name in sorted(cmp.right_only):
            out.append(f"Only in {f'{actual.name}/{rel}'.rstrip('/')}: {name}")
        for name in sorted(cmp.diff_files):
            a, b = Path(cmp.left) / name, Path(cmp.right) / name
            where = f"{rel}/{name}".strip("/")
            out.append(f"diff {where}")
            try:
                out.extend(ln.rstrip("\n") for ln in difflib.unified_diff(
                    a.read_text().splitlines(keepends=True), b.read_text().splitlines(keepends=True),
                    fromfile=f"committed/{where}", tofile=f"now/{where}", n=2))
            except UnicodeDecodeError:
                out.append("(binary files differ)")
        for name, sub in sorted(cmp.subdirs.items()):
            walk(sub, f"{rel}/{name}".strip("/"))

    walk(filecmp.dircmp(expected, actual), "")
    return out[:limit] + ([f"... ({len(out) - limit} more lines)"] if len(out) > limit else [])


def _count_files(lines: list[str]) -> int:
    return sum(1 for ln in lines if ln.startswith(("diff ", "Only in ")))


def _git_archive(root: Path, ref: str, paths: list[str], into: Path) -> bool:
    """``git archive <ref> <paths>`` extracted under ``into``; False when the
    ref or the paths are not there."""
    try:
        proc = subprocess.run(["git", "-C", str(root), "archive", "--format=tar", ref, *paths],  # noqa: S603,S607
                              capture_output=True, check=False)
    except OSError:
        return False
    if proc.returncode != 0 or not proc.stdout:
        return False
    into.mkdir(parents=True, exist_ok=True)
    import io
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tf:
        tf.extractall(into, filter="data")
    return True


def _module_source_base(root: Path) -> str | None:
    try:
        doc = yaml.safe_load((root / "cfg" / "_config.yml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        return None
    cfg = doc.get("config") or {}
    return str(cfg["module_source_base"]) if isinstance(cfg, dict) and cfg.get("module_source_base") else None


def copy_tree_for_a_dry_run(root: Path, work: Path) -> Path:
    """A private copy of the configuration under ``work``: its ``.git``,
    ``generated/`` and ``_private/`` left out. A relative ``module_source_base``
    that escapes the tree (the reference configuration reached the system's
    modules that way until stage 64) is copied beside it at the same relative
    place, so the dry run's ``tofu init`` still finds the modules."""
    base = _module_source_base(root)
    depth = 0
    if base and not base.startswith(("/", "git", "s3::", "gcs::")) and "://" not in base:
        rel = Path(os.path.relpath((root / base).resolve(), root))
        depth = sum(1 for part in rel.parts if part == "..")
    parent = work.joinpath(*(["d"] * depth)) if depth else work
    copy = parent / root.name
    shutil.copytree(root, copy, ignore=shutil.ignore_patterns(".git", "generated", "_private", ".DS_Store"),
                    symlinks=True)
    if depth and base:
        src = (root / base).resolve()
        dst = (copy / base).resolve()
        if src.is_dir() and not dst.exists():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", ".terraform", ".DS_Store"))
    return copy


def subprocess_dry_run(copy: Path) -> None:
    """A headless dry ``run --all`` over ``copy`` in a process of its own (the
    calling process holds no configuration); raises with the log's tail."""
    log_path = copy.parent / "run.log"
    with log_path.open("w") as fh:
        proc = subprocess.run([sys.executable, "-m", "cs_image_system.system", "--root-dir", str(copy),  # noqa: S603
                               "run", "--all"], stdout=fh, stderr=subprocess.STDOUT, check=False)
    if proc.returncode != 0:
        tail = "".join(log_path.read_text().splitlines(keepends=True)[-20:])
        raise RuntimeError(f"the dry run failed (exit {proc.returncode}); the log's tail:\n{tail}")


def config_drift(root: Path, *, dry_run: DryRun | None = None) -> tuple[int, list[str]]:
    """0 when the committed emission is current, 1 (with the diff) when it is
    BEHIND the configuration, 2 when nothing is committed under ``generated/``
    or the dry run itself fails. ``dry_run`` defaults to the subprocess form
    at call time (a test replaces it on the module)."""
    dry_run = dry_run or subprocess_dry_run
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="csis-config-drift.") as tmp:
        work = Path(tmp)
        committed = work / "committed"
        if not _git_archive(root, "HEAD", ["generated"], committed) or not (committed / "generated").is_dir():
            return 2, [f"config-drift: nothing is committed under generated/ at {root} HEAD -- record a run first "
                       "(run --all --commit)"]
        copy = copy_tree_for_a_dry_run(root, work / "tree")
        try:
            dry_run(copy)
        except Exception as e:
            return 2, [f"config-drift: the dry run FAILED: {e}"]
        normalise_emission(committed / "generated")
        normalise_emission(copy / "generated")
        lines = diff_trees(committed / "generated", copy / "generated")
        if not lines:
            return 0, ["config-drift: the committed emission is current with the configuration"]
        return 1, [f"config-drift: the committed emission is BEHIND the configuration ({_count_files(lines)} files):",
                   *lines]


def runtime_unchanged(runtime: str, ref: str = "HEAD") -> tuple[int, list[str]]:
    """0 when the runtime's emission directories (``runtime describe`` ->
    ``emission``) in the working tree equal the same paths at ``ref`` once
    normalised, 1 with the diff when a declaration of that runtime changed,
    2 when the emission directories cannot be read. Needs the configuration
    loaded."""
    from ..global_context import GlobalTypeContext
    from .runtime_facts import emission_dirs
    ctx = GlobalTypeContext()
    root = Path(ctx.working_path).resolve()
    if runtime not in ctx.runtime_builders:
        return 2, [f"runtime-unchanged: no runtime named {runtime!r}"]
    dirs = emission_dirs(ctx, runtime)
    if not dirs:
        return 0, [f"runtime-unchanged: {runtime} has no emission directories under {root / 'generated'}"]
    with tempfile.TemporaryDirectory(prefix="csis-runtime-unchanged.") as tmp:
        work = Path(tmp)
        now, before = work / "now", work / "ref"
        for d in dirs:
            src = root / "generated" / d
            if src.is_dir():
                shutil.copytree(src, now / d)
        _git_archive(root, ref, [f"generated/{d}" for d in dirs], before)
        before_generated = before / "generated"
        before_generated.mkdir(parents=True, exist_ok=True)
        now.mkdir(parents=True, exist_ok=True)
        normalise_emission(now)
        normalise_emission(before_generated)
        lines = diff_trees(before_generated, now)
        if not lines:
            return 0, [f"runtime-unchanged: the emission of {runtime} is unchanged since {ref} ({' '.join(dirs)})"]
        return 1, [f"runtime-unchanged: the emission of {runtime} CHANGED since {ref} ({_count_files(lines)} files):",
                   *lines[:80]]
