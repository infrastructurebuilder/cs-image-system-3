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
The runner scripts lose the two lines only an applying run emits per root
(``apply-check`` and ``tofu apply``; hygiene VIII item 4). Nothing else
legitimately differs: since stage 38 the emission names no absolute path,
so a machine's path appearing here IS drift.

``config_drift`` runs a headless dry ``run --all`` over a private copy of the
configuration and compares its ``generated/`` with the one committed at HEAD,
saying as it goes what it is doing and how long each part took (hygiene XVI
item 1: it was silent for minutes and looked stuck).
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
import time
from functools import partial
from pathlib import Path
from typing import Callable

import yaml

from ..constants import RUN_LOCAL_FILENAMES

log = logging.getLogger(__name__)

# names pruned wherever they are, and path suffixes pruned
RESIDUE_NAMES: tuple[str, ...] = (".terraform", ".terraform.lock.hcl", "tfplan", "temp_assets",
                                  "csis-sanctioned-removals.txt",        # hygiene XII item 24: a runner's step's, never the emission's
                                  *RUN_LOCAL_FILENAMES)
RESIDUE_SUFFIXES: tuple[str, ...] = ("release/release", "retention/retention")
RUN_ID = re.compile(rb"[0-9]{4}_[0-9]{2}_[0-9]{2}t[0-9]{2}_[0-9]{2}_[0-9]{2}_[0-9]{6}")
STAMP = re.compile(rb"[0-9]{8}[-_][0-9]{6}")
RUN_PLACEHOLDER = b"<RUN>"
STAMP_PLACEHOLDER = b"<STAMP>"
# hygiene VIII item 4: an APPLYING run (--apply-runtime) emits, per root, an
# apply-check line and a `tofu apply` line that a resting generation does not,
# and commits the script it executed. They are a function of the invocation,
# not of the configuration, so the comparison drops them from the runner
# scripts on both sides -- found when a cloud-launch's commit failed the next
# config-drift as "BEHIND the configuration (1 files)".
APPLY_ONLY = re.compile(rb"^[^\n]*(?:cs-image-system apply-check |tofu apply -input=false)[^\n]*\n?", re.M)


def _is_runner_script(path: Path) -> bool:
    return path.suffix == ".sh" and (path.name.startswith("run-") or path.name == "final_execution.sh")

DryRun = Callable[[Path], None]
Progress = Callable[[str], None]

#: hygiene XVI item 2: the provider cache a starter's Justfile keeps inside the
#: tree (``TF_PLUGIN_CACHE_DIR``) holds every provider version the tree ever
#: fetched -- 5.7 GB in the reference configuration on 2026-10-27, when the copy
#: filled the disk. The copy's dry run never reads it: the child process inherits
#: ``TF_PLUGIN_CACHE_DIR``, which still names the original tree's cache.
PROVIDER_CACHE = ".tofu-plugin-cache"
LEFT_OUT_OF_THE_COPY: tuple[str, ...] = (".git", "generated", "_private", ".DS_Store", PROVIDER_CACHE)

#: the dry run's log lines that say where it is (both logged at INFO by the run;
#: the rich handler starts a record with its time, or blanks for the same second,
#: then the level). Anchored at the start of the line, so the indented output of a
#: step the run captured never counts.
_RECORD = r"^(?:\[[^\]\n]{1,16}\]\s?|\s{0,17})INFO\s+"
LIFECYCLE_LINE = re.compile(_RECORD + r"\[(?P<lifecycle>[\w-]+)\] regenerating\b")
INIT_LINE = re.compile(_RECORD + r"(?P<tool>tofu|packer) init stdout(?::| \(last )")


def _took(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"


class DryRunProgress:
    """Reads the dry run's log line by line and says, through ``say``, each
    lifecycle as it starts and each root's ``init`` (the slow part: providers
    are installed per root), with the time since the dry run started."""

    def __init__(self, say: Progress, clock: Callable[[], float] = time.monotonic) -> None:
        self.say = say
        self.clock = clock
        self.started = clock()
        self.lifecycle: str | None = None
        self.lifecycles = 0
        self.inits = 0

    def _at(self) -> str:
        return _took(self.clock() - self.started)

    def feed(self, line: str) -> None:
        m = LIFECYCLE_LINE.match(line)
        if m:
            self.lifecycle = m["lifecycle"]
            self.lifecycles += 1
            self.say(f"config-drift: [{self.lifecycle}] generating ({self._at()} into the dry run)")
            return
        m = INIT_LINE.match(line)
        if m:
            self.inits += 1
            self.say(f"config-drift:   [{self.lifecycle or '-'}] {m['tool']} init {self.inits} "
                     f"({self._at()} into the dry run)")

    def done(self, ok: bool) -> None:
        self.say(f"config-drift: the dry run {'finished' if ok else 'FAILED'} after {self._at()} "
                 f"({self.lifecycles} lifecycle(s), {self.inits} init(s))")


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
            if _is_runner_script(path):
                new = APPLY_ONLY.sub(b"", new)
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


def _provider_cache_inside(root: Path) -> Path | None:
    """The directory ``TF_PLUGIN_CACHE_DIR`` names, when it lies inside ``root``."""
    value = os.environ.get("TF_PLUGIN_CACHE_DIR")
    if not value:
        return None
    cache = Path(value).expanduser()
    cache = (cache if cache.is_absolute() else Path.cwd() / cache).resolve()
    root = root.resolve()
    return cache if cache != root and cache.is_relative_to(root) else None


def _left_out_of_the_copy(root: Path) -> Callable[[str, list[str]], set[str]]:
    """The ``ignore`` for the copy: the names in ``LEFT_OUT_OF_THE_COPY`` at any
    depth, and the provider cache ``TF_PLUGIN_CACHE_DIR`` names in the tree."""
    by_name = shutil.ignore_patterns(*LEFT_OUT_OF_THE_COPY)
    cache = _provider_cache_inside(root)

    def ignore(directory: str, names: list[str]) -> set[str]:
        out = set(by_name(directory, names))
        if cache is not None and cache.name in names and Path(directory).resolve() == cache.parent:
            out.add(cache.name)
        return out
    return ignore


def copy_tree_for_a_dry_run(root: Path, work: Path) -> Path:
    """A private copy of the configuration under ``work``: its ``.git``,
    ``generated/``, ``_private/`` and provider cache left out (the cache by its
    starter name, ``.tofu-plugin-cache``, and as ``TF_PLUGIN_CACHE_DIR`` names
    it when that lies inside the tree). A relative ``module_source_base``
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
    shutil.copytree(root, copy, ignore=_left_out_of_the_copy(root), symlinks=True)
    if depth and base:
        src = (root / base).resolve()
        dst = (copy / base).resolve()
        if src.is_dir() and not dst.exists():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", ".terraform", ".DS_Store"))
    return copy


def subprocess_dry_run(copy: Path, progress: Progress | None = None, command: list[str] | None = None) -> None:
    """A headless dry ``run --all`` over ``copy`` in a process of its own (the
    calling process holds no configuration); raises with the log's tail. Its
    output goes to ``run.log`` beside the copy, line by line as it is written,
    and ``progress`` hears where it is (``DryRunProgress``). ``command``
    replaces the run, for a test."""
    log_path = copy.parent / "run.log"
    tracker = DryRunProgress(progress) if progress else None
    argv = command or [sys.executable, "-m", "cs_image_system.system", "--root-dir", str(copy), "run", "--all"]
    with log_path.open("w") as fh:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,  # noqa: S603
                                text=True, errors="replace", env={**os.environ, "PYTHONUNBUFFERED": "1"})
        assert proc.stdout is not None
        for line in proc.stdout:
            fh.write(line)
            if tracker:
                tracker.feed(line)
        code = proc.wait()
    if tracker:
        tracker.done(code == 0)
    if code != 0:
        tail = "".join(log_path.read_text().splitlines(keepends=True)[-20:])
        raise RuntimeError(f"the dry run failed (exit {code}); the log's tail:\n{tail}")


def _size(tree: Path) -> tuple[int, int]:
    files = size = 0
    for dirpath, _dirs, names in os.walk(tree):
        for name in names:
            try:
                size += (Path(dirpath) / name).lstat().st_size
            except OSError:
                continue
            files += 1
    return files, size


def config_drift(root: Path, *, dry_run: DryRun | None = None,
                 progress: Progress | None = None) -> tuple[int, list[str]]:
    """0 when the committed emission is current, 1 (with the diff) when it is
    BEHIND the configuration, 2 when nothing is committed under ``generated/``
    or the dry run itself fails. ``dry_run`` defaults to the subprocess form
    at call time (a test replaces it on the module). ``progress`` hears what
    it is doing as it goes, each part with its time (hygiene XVI item 1)."""
    say: Progress = progress or (lambda _line: None)
    dry_run = dry_run or partial(subprocess_dry_run, progress=say)
    root = Path(root).resolve()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="csis-config-drift.") as tmp:
        work = Path(tmp)
        committed = work / "committed"
        if not _git_archive(root, "HEAD", ["generated"], committed) or not (committed / "generated").is_dir():
            return 2, [f"config-drift: nothing is committed under generated/ at {root} HEAD -- record a run first "
                       "(run --all --commit)"]
        say(f"config-drift: copying {root} for a dry run (without .git, generated/, _private/ "
            "and the provider cache)")
        mark = time.monotonic()
        copy = copy_tree_for_a_dry_run(root, work / "tree")
        files, size = _size(copy)
        say(f"config-drift: copied {files} files ({size / 1e6:.1f} MB) in {_took(time.monotonic() - mark)}")
        say("config-drift: a dry run of every lifecycle over the copy, in a process of its own; "
            "each root's init installs its providers, so this takes minutes")
        try:
            dry_run(copy)
        except Exception as e:
            return 2, [f"config-drift: the dry run FAILED: {e}"]
        say("config-drift: comparing the copy's generated/ with the one committed at HEAD")
        normalise_emission(committed / "generated")
        normalise_emission(copy / "generated")
        lines = diff_trees(committed / "generated", copy / "generated")
        say(f"config-drift: {_took(time.monotonic() - started)} in all")
        if not lines:
            return 0, ["config-drift: the committed emission is current with the configuration"]
        moved = vendor_image_moves(lines)
        if moved:
            # hygiene XII item 27 (the walk's F55): the emission of a base that has
            # no build yet names the vendor's newest image as the day's generation
            # resolved it; when the vendor publishes again the committed emission is
            # behind by that one line, with no change by anyone, and the scheduled
            # run went red for it. Not a change of the tree's: said in one line.
            return 0, ["config-drift: the committed emission is current with the configuration, but the vendor's "
                       f"newest image moved under a base this tree has not baked ({len(moved)} line(s)); "
                       "nothing of yours changed, and `just record` takes it:", *moved]
        return 1, [f"config-drift: the committed emission is BEHIND the configuration ({_count_files(lines)} files):",
                   *lines]


#: the lines of a base's packer source that name the vendor's image as resolved at generation
VENDOR_IMAGE_LINE = re.compile(r'^[-+]\s*(?:image-id|source_image|source_image_name|image_name)\s*=\s*"[^"]*",?\s*$')


def vendor_image_moves(lines: list[str]) -> list[str]:
    """When every differing file is a base's packer source under ``base-image/``
    and every changed line names the vendor's image, the moves (``file: old ->
    new``); else an empty list, and the diff is the tree's own. A diff
    ``diff_trees`` cut short is never a move: what it left out may be
    anything (hygiene XVII item 1)."""
    moves: list[str] = []
    current: str | None = None
    olds: list[str] = []
    news: list[str] = []

    def flush() -> None:
        if current is not None:
            if len(olds) != len(news):
                raise ValueError("unpaired")
            for a, b in zip(olds, news):
                moves.append(f"{current}: {a} -> {b}")
    try:
        for ln in lines:
            if ln.startswith(("Only in ", "... (", "(binary files differ)")):
                return []
            if ln.startswith("diff "):
                flush()
                current = ln[5:].strip()
                olds, news = [], []
                if not current.startswith("base-image/") or "image-generation" not in current:
                    return []
                continue
            if ln.startswith(("---", "+++", "@@")) or not ln.startswith(("-", "+")):
                continue
            if not VENDOR_IMAGE_LINE.match(ln):
                return []
            (olds if ln.startswith("-") else news).append(ln[1:].strip().rstrip(","))
        flush()
    except ValueError:
        return []
    return moves


def runtime_unchanged(runtime: str, ref: str = "HEAD") -> tuple[int, list[str]]:
    """0 when the runtime's emission directories (``runtime describe`` ->
    ``emission``) in the working tree equal the same paths at ``ref`` once
    normalised, or differ only by the vendor's newest image under a base not
    yet baked (said, with the moves; hygiene XVII item 1), 1 with the diff
    when a declaration of that runtime changed, 2 when the emission
    directories cannot be read. Needs the configuration loaded."""
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
        moved = vendor_image_moves(lines)
        if moved:
            # hygiene XVII item 1: the vendor publishing under a base with no build yet is
            # no declaration of the runtime's -- config-drift's reading (hygiene XII item 27);
            # nothing is there to apply by hand, and the guard failed perform for it
            return 0, [f"runtime-unchanged: the emission of {runtime} is unchanged since {ref} ({' '.join(dirs)}), "
                       f"but the vendor's newest image moved under a base this tree has not baked "
                       f"({len(moved)} line(s)); nothing of yours changed:", *moved]
        return 1, [f"runtime-unchanged: the emission of {runtime} CHANGED since {ref} ({_count_files(lines)} files):",
                   *lines[:80]]
