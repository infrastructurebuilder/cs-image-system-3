# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What the checkout can tell the interview without loading anything: the
repository from ``git remote``, its ids from ``gh api`` when ``gh`` is there,
the runtimes, the team and the module source base from the raw ``cfg/*.yml``
(read as YAML, never templated or validated -- the sessions and federation
the bootstrap makes may not exist yet, so the tree is not loaded).
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

log = logging.getLogger(__name__)

#: What a starter tree carries where a team's value goes. A default that is
#: still one of these was never filled in, so it is no default at all.
PLACEHOLDER_MARKS = ("REPLACE-ME", "REPLACE_ME", "123456789012")


def is_placeholder(value: Any) -> bool:
    return value is None or any(mark in str(value) for mark in PLACEHOLDER_MARKS) or str(value).strip() == ""


def real(value: Any) -> str | None:
    """The value as text, or None when it is empty or a starter placeholder."""
    return None if is_placeholder(value) else str(value).strip()


def run_tool(args: list[str], timeout: int = 60) -> tuple[int, str]:
    """A read-only probe of the account (``aws iam get-role``, say): the exit
    code and the output; 127 when the tool is not installed, 124 on a
    timeout. A section's default asks through ``Facts.probe`` so a test can
    answer instead."""
    if shutil.which(args[0]) is None:
        return 127, ""
    try:
        res = subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError:
        return 127, ""
    return res.returncode, (res.stdout or "") + (res.stderr or "")


_REMOTE = re.compile(r"(?:git@github\.com:|https://github\.com/)(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")


@dataclass
class Facts:
    config_root: Path
    remote_url: str | None = None
    owner: str | None = None
    repo: str | None = None
    owner_id: int | None = None
    repo_id: int | None = None
    default_branch: str | None = None
    runtimes: list[dict[str, Any]] = field(default_factory=list)
    team: str | None = None
    module_source_base: str = "tfmodules"
    state_backends: list[dict[str, Any]] = field(default_factory=list)
    probe: Callable[..., tuple[int, str]] = field(default=run_tool, repr=False, compare=False)

    @property
    def repository(self) -> str | None:
        return f"{self.owner}/{self.repo}" if self.owner and self.repo else None


def parse_remote(url: str | None) -> tuple[str, str] | None:
    """``owner, repo`` from a GitHub remote in either form, else None."""
    if not url:
        return None
    m = _REMOTE.match(url.strip())
    return (m.group("owner"), m.group("repo")) if m else None


def _git(root: Path, *args: str) -> str | None:
    try:
        res = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return res.stdout.strip() if res.returncode == 0 else None


def _gh_id(path: str) -> int | None:
    if shutil.which("gh") is None:
        return None
    try:
        res = subprocess.run(["gh", "api", path, "--jq", ".id"], capture_output=True, text=True, check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    try:
        return int(res.stdout.strip()) if res.returncode == 0 else None
    except ValueError:
        return None


def raw_yaml(path: Path) -> dict[str, Any]:
    """A ``cfg/*.yml`` file as plain YAML; an unreadable or templated file
    that YAML cannot parse yields nothing rather than an error -- these are
    defaults, not declarations."""
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def collect(cfg: Path, key: str, *, named: bool = True) -> list[dict[str, Any]]:
    """Every entry under ``key`` in ANY ``cfg/*.yml``, in file-name order. The
    loader reads the whole directory -- a tree may keep its default state
    backend in ``state-backends-2.yml`` beside a non-default one in
    ``state-backends.yml`` (the reference configuration does, and reading
    the one canonical file named the wrong bucket as the tree's on
    2026-10-01) -- so the defaults must look where the loader looks."""
    out: list[dict[str, Any]] = []
    for path in sorted([*cfg.glob("*.yml"), *cfg.glob("*.yaml")]):
        entries = raw_yaml(path).get(key)
        if isinstance(entries, list):
            out.extend(e for e in entries if isinstance(e, dict) and (e.get("name") or not named))
    return out


def gather(config_root: Path, *, git: bool = True, gh: bool = True) -> Facts:
    root = Path(config_root)
    facts = Facts(config_root=root)
    if git:
        facts.remote_url = _git(root, "remote", "get-url", "origin")
        parsed = parse_remote(facts.remote_url)
        if parsed:
            facts.owner, facts.repo = parsed
        head = _git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
        if head and "/" in head:
            facts.default_branch = head.split("/", 1)[1]
    if gh and facts.repository:
        facts.repo_id = _gh_id(f"repos/{facts.repository}")
        facts.owner_id = _gh_id(f"users/{facts.owner}")
    cfg = root / "cfg"
    facts.runtimes = collect(cfg, "runtime_builders")
    teams = [str(g["team"]) for g in collect(cfg, "group_builders", named=False) if g.get("team")]
    facts.team = teams[0] if teams else None
    config = raw_yaml(cfg / "_config.yml").get("config")
    if isinstance(config, dict) and config.get("module_source_base"):
        facts.module_source_base = str(config["module_source_base"])
    facts.state_backends = collect(cfg, "state_backends")
    return facts


def runtime_of_type(facts: Facts, kind: str) -> dict[str, Any] | None:
    """The tree's runtime of a cloud (``aws``, ``gcloud``): the default one of
    that type, else the first."""
    mine = [r for r in facts.runtimes if str(r.get("type", "")).lower() == kind]
    return next((r for r in mine if r.get("is_default")), mine[0] if mine else None)


def default_state_backend(facts: Facts, kind: str = "s3") -> dict[str, Any] | None:
    """The tree's declared state backend of a type: the default, else the first."""
    mine = [b for b in facts.state_backends if str(b.get("type", "")).lower() == kind]
    return next((b for b in mine if b.get("is_default")), mine[0] if mine else None)


def first_runtime_name(facts: Facts, *, prefer: tuple[str, ...] = ("aws",)) -> str | None:
    """The default runtime's name: the one marked ``is_default``, else the
    first whose type or aliases name a preferred cloud, else the first."""
    if not facts.runtimes:
        return None
    for r in facts.runtimes:
        if r.get("is_default"):
            return str(r["name"])
    for r in facts.runtimes:
        words = {str(r.get("type", "")).lower(), *(str(a).lower() for a in (r.get("aliases") or []))}
        if any(p in words for p in prefer):
            return str(r["name"])
    return str(facts.runtimes[0]["name"])


def runtime_region(facts: Facts, name: str | None) -> str | None:
    for r in facts.runtimes:
        if name and r.get("name") == name:
            region = r.get("region") or (r.get("config") or {}).get("region") if isinstance(r.get("config"), dict) else r.get("region")
            return str(region) if region else None
    return None
