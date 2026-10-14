# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The private mirror an execution runs from (stage 49).

The committed emission under ``generated/`` carries the ``ENC[age:...]``
ciphertext wherever the configuration did. The tools cannot read that, so
before a deferred command runs, its root is copied into

    <configuration root>/_private/<the same relative path>

with every embedded marker replaced by its plaintext. ``_private/`` is a
SIBLING of ``generated/`` at the same depth, which matters: the ``local``
state type renders its path relative to the root by counting directories
(``ROOT_DEPTH``), so a mirror one level deeper would point every local-state
root at nothing.

Nothing in the mirror is ever committed -- it is a refused path by name, it is
named in the emitted ``.gitignore``, and the public-safe scanner skips it. It
is left in place after a local run, so the operator can read what actually
ran; CI removes it in a step of its own that runs even when the build failed.
"""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Iterable

from .encryption import MARKER_PREFIX, substitute_markers

log = logging.getLogger(__name__)

#: The mirror's directory name, beside ``generated/`` under the config root.
PRIVATE_DIRNAME = "_private"

#: Suffixes copied byte-for-byte: a marker cannot occur in them, and reading
#: them as text would corrupt them.
BINARY_SUFFIXES = frozenset({
    ".zip", ".gz", ".tgz", ".bz2", ".xz", ".tar", ".png", ".jpg", ".jpeg",
    ".gif", ".ico", ".pdf", ".so", ".dylib", ".dll", ".exe", ".bin", ".p12",
})


#: What the configuration root's own .gitignore must say about the mirror. It
#: cannot live in the emitted `generated/.gitignore`: a .gitignore's patterns
#: are relative to its own directory, and the mirror is `generated/`'s SIBLING.
IGNORE_LINE = f"{PRIVATE_DIRNAME}/"
IGNORE_NOTE = "# the private mirror an execution runs from (never committed)"


def private_root(config_root: Path) -> Path:
    return Path(config_root) / PRIVATE_DIRNAME


def ensure_ignored(config_root: Path) -> bool:
    """Make the configuration root ignore the mirror. True when a line was added.

    The system creates ``_private/`` inside the operator's repository, so the
    system says it is not to be committed. The commit gate refuses it and the
    run excludes it by pathspec either way -- but without this git lists it as
    untracked and ``git add -A`` stages it, leaving the operator a refusal to
    understand instead of an accident that could not happen.

    Additive and idempotent: an existing ``.gitignore`` is appended to, never
    rewritten, and a root that is not a git repository is left alone."""
    root = Path(config_root)
    if not (root / ".git").exists():
        return False
    ignore = root / ".gitignore"
    existing = ignore.read_text() if ignore.is_file() else ""
    if any(line.strip().rstrip("/") == PRIVATE_DIRNAME for line in existing.splitlines()):
        return False
    prefix = "" if (not existing or existing.endswith("\n")) else "\n"
    ignore.write_text(f"{existing}{prefix}{IGNORE_NOTE}\n{IGNORE_LINE}\n")
    log.info("added '%s' to %s: the mirror is never committed", IGNORE_LINE, ignore)
    return True


def mirror_path(config_root: Path, path: Path) -> Path:
    """Where ``path`` (under the configuration root) is materialised.

    ``_private/`` stands exactly where ``generated/`` stands: the generation
    directory's own name is REPLACED, not nested under. That keeps every
    materialised root at the SAME DEPTH below the configuration root as the
    root it mirrors, which is what makes the relative paths in the emission
    keep resolving -- a module source
    (``../../../../../cs-image-system-3/tfmodules/...``) and the ``local``
    state type's ``../../../../<dir>/<ws>.tfstate`` both count directories up
    to the configuration root, and one extra level breaks both. Found by
    probing an AZ change, 2026-09-19: ``tofu init`` in the mirror could not
    read its module.

    A path already inside the mirror is returned unchanged, so materialising
    twice is harmless."""
    config_root, path = Path(config_root).resolve(), Path(path).resolve()
    rel = path.relative_to(config_root)
    if rel.parts and rel.parts[0] == PRIVATE_DIRNAME:
        return path
    # drop the generation directory's name (whatever it is called) and put
    # the mirror in its place
    return private_root(config_root).joinpath(*rel.parts[1:])


def _is_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_SUFFIXES:
        return True
    try:
        return b"\0" in path.read_bytes()[:8192]
    except OSError:
        return True


def materialize_file(src: Path, dst: Path, identities: Iterable | None = None) -> bool:
    """Copy one file, substituting markers. True when anything was substituted."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if _is_binary(src):
        shutil.copy2(src, dst)
        return False
    text = src.read_text()
    if MARKER_PREFIX not in text:
        shutil.copy2(src, dst)
        return False
    dst.write_text(substitute_markers(text, identities))
    shutil.copystat(src, dst)
    return True


#: What the mirror records about itself: the relative paths materialize wrote
#: last time, so a file dropped from the emission can be dropped here too
#: WITHOUT touching what the tools produced (``.terraform/``, ``tfplan``,
#: ``manifest.json``, a local state file). The mirror is re-materialised before
#: every deferred command of a root, so it must be incremental: wiping it would
#: destroy the plan between ``plan`` and ``apply``.
MANIFEST_NAME = ".csis-materialized"

#: Files produced IN the mirror that belong in the committed emission. The lock
#: file pins provider hashes and carries no secret (the scanner treats its
#: ``h1:``/``zh:`` hashes as public by structure); ``init`` writes it where it
#: runs, which is now the mirror, so it is copied back. Nothing else ever is.
SYNC_BACK = (".terraform.lock.hcl",)


def _read_manifest(dst: Path) -> set[str]:
    f = dst / MANIFEST_NAME
    if not f.is_file():
        return set()
    return {line for line in f.read_text().splitlines() if line}


def materialize(src: Path, dst: Path, identities: Iterable | None = None) -> tuple[int, int]:
    """Materialise ``src`` (a file or a directory) into ``dst``.

    Returns (files written, files in which a marker was substituted).
    INCREMENTAL by design: what the tools wrote in the mirror survives, because
    a terraform root is materialised again before each of its commands and
    ``apply`` must still find the ``tfplan`` that ``plan`` wrote. Only files
    this function wrote before, and that the emission no longer has, are
    removed."""
    src, dst = Path(src), Path(dst)
    if not src.exists():
        raise FileNotFoundError(f"nothing to materialize at {src}")
    if src.is_file():
        return (1, 1 if materialize_file(src, dst, identities) else 0)
    previous = _read_manifest(dst)
    current: set[str] = set()
    written = substituted = 0
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        rel = str(path.relative_to(src))
        current.add(rel)
        if materialize_file(path, dst / rel, identities):
            substituted += 1
        written += 1
    for stale in sorted(previous - current):
        target = dst / stale
        if target.is_file():
            target.unlink()
    dst.mkdir(parents=True, exist_ok=True)
    (dst / MANIFEST_NAME).write_text("".join(f"{r}\n" for r in sorted(current)))
    log.debug("materialized %s -> %s (%d files, %d with ciphertext)", src, dst, written, substituted)
    return (written, substituted)


def sync_back(src: Path, dst: Path) -> list[str]:
    """Copy the few tool outputs that belong in the committed emission back out
    of the mirror (:data:`SYNC_BACK`), and name what moved.

    This is the ONLY direction anything travels from the mirror, and the
    allowlist is what makes that safe: a plan, a state file or a manifest holds
    the plaintext and stays where it was written."""
    moved: list[str] = []
    for path in sorted(Path(dst).rglob("*")):
        if not path.is_file() or path.name not in SYNC_BACK:
            continue
        target = Path(src) / path.relative_to(dst)
        if target.is_file() and target.read_bytes() == path.read_bytes():
            continue
        if target.is_file() and path.name == ".terraform.lock.hcl":
            # hygiene XII item 30 (the walk's F60): `init` records the hashes of
            # the provider packages it verified, which differ by where it ran (the
            # plugin cache, the platform), so a record from CI and one from a
            # person's machine took fourteen `h1:` lines from each other in turn.
            # The committed lock is the UNION of what both have seen, and the
            # mirror is brought level so the next init starts from it.
            merged = merge_lock_files(target.read_text(), path.read_text())
            path.write_text(merged)
            if merged == target.read_text():
                continue
            target.write_text(merged)
            moved.append(str(path.relative_to(dst)))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        moved.append(str(path.relative_to(dst)))
    return moved


_LOCK_PROVIDER = re.compile(r'^provider "([^"]+)" \{$')


def merge_lock_files(committed: str, fresh: str) -> str:
    """The provider lock file ``fresh`` wrote, with every hash ``committed``
    had for the same provider at the same version kept. Versions and
    constraints are the fresh file's (the init that just ran); a provider only
    the committed file names is kept whole."""
    def parse(text: str) -> tuple[list[str], dict[str, tuple[str, str, list[str]]], list[str]]:
        head: list[str] = []
        order: list[str] = []
        blocks: dict[str, tuple[str, str, list[str]]] = {}
        name: str | None = None
        version = constraints = ""
        hashes: list[str] = []
        in_hashes = False
        for ln in text.splitlines():
            m = _LOCK_PROVIDER.match(ln)
            if m:
                name, version, constraints, hashes, in_hashes = m.group(1), "", "", [], False
                continue
            if name is None:
                head.append(ln)
                continue
            s = ln.strip()
            if s.startswith("version"):
                version = ln
            elif s.startswith("constraints"):
                constraints = ln
            elif s.startswith("hashes = ["):
                in_hashes = True
            elif in_hashes and s.startswith("]"):
                in_hashes = False
            elif in_hashes and s.startswith('"'):
                hashes.append(s.rstrip(",").strip('"'))
            elif s == "}":
                order.append(name)
                blocks[name] = (version, constraints, hashes)
                name = None
        while head and not head[-1].strip():
            head.pop()
        return head, blocks, order
    head, old, old_order = parse(committed)
    fhead, new, new_order = parse(fresh)
    out = list(fhead or head)
    seen: set[str] = set()
    for name in [*new_order, *(n for n in old_order if n not in new)]:
        if name in seen:
            continue
        seen.add(name)
        version, constraints, hashes = new.get(name) or old[name]
        union = list(hashes)
        if name in new and name in old and old[name][0].strip() == version.strip():
            union += [h for h in old[name][2] if h not in union]
        h1 = sorted(h for h in union if h.startswith("h1:"))
        zh = sorted(h for h in union if h.startswith("zh:"))
        rest = [h for h in union if not h.startswith(("h1:", "zh:"))]
        out.append("")
        out.append(f'provider "{name}" {{')
        out.append(version)
        if constraints:
            out.append(constraints)
        out.append("  hashes = [")
        out.extend(f'    "{h}",' for h in [*h1, *zh, *rest])
        out.append("  ]")
        out.append("}")
    return "\n".join(out).rstrip("\n") + "\n"
