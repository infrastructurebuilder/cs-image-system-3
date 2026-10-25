# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Links in a starter that lead out of it (hygiene XV item 1; stage 66).

A starter's Markdown is written where it lives, under ``docs/examples/<name>``
in the system repository, and links into that repository by relative path
(``../../CONFIGURATION.md``, ``../standard-aws/README.md``). A tree made from
the starter -- by ``init-config`` or as a template repository -- stands
alone, where those paths point nowhere. Each such link becomes a link to the
same file in the system repository at the release's tag; a link that stays
inside the starter, a URL and an anchor stand as written.
"""
from __future__ import annotations

import posixpath
import re
from pathlib import Path

SYSTEM_REPO = "infrastructurebuilder/cs-image-system-3"
LINK = re.compile(r"\]\((?P<target>[^)\s]+)\)")


def rewrite_links(text: str, file_dir: str, tree: str, version: str) -> str:
    """``text``'s links that leave ``tree``, resolved from ``file_dir`` (both
    repository-relative POSIX paths), pointed at the system repository at
    ``v<version>``; the rest stand as written."""
    def one(m: re.Match) -> str:
        target = m["target"]
        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith(("#", "/")):
            return m.group(0)                      # a URL, an anchor, a site-absolute path
        path, _, anchor = target.partition("#")
        resolved = posixpath.normpath(posixpath.join(file_dir, path))
        if resolved == tree or resolved.startswith(tree + "/") or resolved.startswith(".."):
            return m.group(0)
        kind = "tree" if path.endswith("/") or "." not in posixpath.basename(resolved) else "blob"
        return f"](https://github.com/{SYSTEM_REPO}/{kind}/v{version}/{resolved}{'#' + anchor if anchor else ''})"
    return LINK.sub(one, text)


def rewrite_tree(root: Path, starter: str, version: str) -> list[str]:
    """Rewrite every Markdown file of a tree made from ``starter`` (its root at
    ``root``; ``.git`` left alone); the files that changed, relative to it."""
    tree = f"docs/examples/{starter}"
    changed: list[str] = []
    for md in sorted(root.rglob("*.md")):
        rel = md.relative_to(root).as_posix()
        if rel.split("/", 1)[0] == ".git":
            continue
        text = md.read_text()
        new = rewrite_links(text, posixpath.dirname(f"{tree}/{rel}"), tree, version)
        if new != text:
            md.write_text(new)
            changed.append(rel)
    return changed
