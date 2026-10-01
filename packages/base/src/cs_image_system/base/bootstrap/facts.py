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
from typing import Any

import yaml

log = logging.getLogger(__name__)

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
    runtimes = raw_yaml(cfg / "runtime-builders.yml").get("runtime_builders")
    if isinstance(runtimes, list):
        facts.runtimes = [r for r in runtimes if isinstance(r, dict) and r.get("name")]
    groups = raw_yaml(cfg / "group-builders.yml").get("group_builders")
    if isinstance(groups, list):
        teams = [str(g["team"]) for g in groups if isinstance(g, dict) and g.get("team")]
        facts.team = teams[0] if teams else None
    config = raw_yaml(cfg / "_config.yml").get("config")
    if isinstance(config, dict) and config.get("module_source_base"):
        facts.module_source_base = str(config["module_source_base"])
    return facts


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
