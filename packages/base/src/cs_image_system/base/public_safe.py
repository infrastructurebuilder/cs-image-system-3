# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Public-safe by construction (stage 35): one scanner behind the commit-time
gate, ``just public-safe``, the plain pre-commit hook, and the meta-state and
state-report writes.

It reads BYTES -- a zipped ``tfplan`` is opened and its members scanned, a
gzip member likewise -- so a compressed plan is scanned, not skipped. It
knows the shapes that must never be public (``HARD_RULES``: keys, tokens,
PEM bodies, a service-account file, a ``TF_VAR_*=`` assignment with a value,
an age identity) and the shapes that are usually private (``SOFT_RULES``: an
email address, a long mixed-case base64 string), and it refuses some paths
outright whatever they hold (``REFUSED_PATHS``: plans, state, tfvars,
``.envrc``, key material). Structural public material is blanked before the
rules run: ``ENC[age:...]`` ciphertext, age public keys, lock-file hashes,
SSH public keys.

Allowances are by decision, not by silence: ``cfg/_config.yml``
``public_safe.allow`` lists substrings the operator accepted as public with
the reason beside each (a domain whose addresses are public by
construction, a service account's address), and ``path:<glob>`` entries
for a file accepted whole (the frozen fixture's TEST identity). Prose and
test code (``*.md``, ``docs/``, ``tests/**/*.py``) are exempt from the soft
rules only: a fake address in a test is noise, a PEM body anywhere is not.
"""
from __future__ import annotations

import fnmatch
import gzip
import io
import re
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import yaml

# ----------------------------------------------------------------- by path
# Never committed, by name at any depth: plans and state hold the decrypted
# values the emission refers to; tfvars carry values; key material and the
# credentials file never belong in a public repository.
REFUSED_PATHS = ("tfplan", "*.tfplan", "*.tfstate", "*.tfstate.*", "*.tfvars", "*.tfvars.json",
                 ".envrc", "*.pem", ".private_key.*", ".public_key.json")

# The private mirror (stage 49): the materialised copy an execution runs from,
# holding the plaintext of every value the emission carries as ciphertext.
# Refused as a whole subtree, not by file name, because anything may be in it.
PRIVATE_DIRNAME = "_private"

# The soft rules skip prose and test modules; every hard rule applies everywhere.
SOFT_EXEMPT = ("*.md", "docs/*", "tests/*.py", "*/tests/*.py", "test_*.py", "conftest.py")


def refused_path(path: str | Path) -> bool:
    """True when ``path`` (any depth) is one nothing may commit."""
    path = Path(path)
    if PRIVATE_DIRNAME in path.parts:
        return True
    return any(fnmatch.fnmatch(path.name, pat) for pat in REFUSED_PATHS)


def soft_exempt(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    name = Path(rel).name
    return any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat) for pat in SOFT_EXEMPT)


# ------------------------------------------------------------------ rules
Rule = Callable[[bytes], list[tuple[int, int]]]


def _regex(pattern: bytes) -> Rule:
    rx = re.compile(pattern)
    return lambda data: [m.span() for m in rx.finditer(data)]


def _service_account_file(data: bytes) -> list[tuple[int, int]]:
    """A GCP service-account JSON: its ``private_key_id`` with a value, or the
    ``type`` marker in a document that also carries a private key (the bare
    marker alone is what documentation says when it names the shape)."""
    spans = [m.span() for m in re.finditer(rb'"private_key_id"\s*:\s*"[0-9a-f]{20,}"', data)]
    if b'"private_key"' in data:
        spans += [m.span() for m in re.finditer(rb'"type"\s*:\s*"service_account"', data)]
    return spans


HARD_RULES: dict[str, Rule] = {
    "jwt": _regex(rb"eyJ[A-Za-z0-9_-]{20,}"),          # no boundary: a plan's binary glues it to anything
    "pem-private-key": _regex(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "aws-access-key": _regex(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "gcp-service-account": _service_account_file,
    "slack-token": _regex(rb"\bxox[baprs]-[0-9A-Za-z-]{10,}"),
    "github-token": _regex(rb"\bgh[pousr]_[0-9A-Za-z]{20,}\b"),
    "age-identity": _regex(rb"\bAGE-SECRET-KEY-1[A-Z0-9]{58}\b"),
    # an assignment with a literal value; `TF_VAR_x=$FROM_ENV` and `TF_VAR_x="${...}"` pass
    "tfvar-assignment": _regex(rb"\bTF_VAR_\w+=(?![\"']?\$)[^\s\"']{4,}"),
    # the packer equivalent (stage 49): a run script may pass a materialised
    # value as PKR_VAR_x="$(...)", never as a literal
    "pkrvar-assignment": _regex(rb"\bPKR_VAR_\w+=(?![\"']?\$)[^\s\"']{4,}"),
}

_EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_EXAMPLE_DOMAINS = (b"example.com", b"example.org", b"example.net", b".invalid", b".test", b"localhost")


def _email(data: bytes) -> list[tuple[int, int]]:
    out = []
    for m in _EMAIL.finditer(data):
        dom = m.group(1).lower()
        if any(dom == d.lstrip(b".") or dom.endswith(d) for d in _EXAMPLE_DOMAINS):
            continue
        out.append(m.span())
    return out


SOFT_RULES: dict[str, Rule] = {
    "email": _email,
    # forty or more base64 characters with lower case, upper case and digits:
    # the shape of a key or a token; digests are hex and fall outside it
    "high-entropy": _regex(rb"(?<![A-Za-z0-9+/])(?=[A-Za-z0-9+/]*[a-z])(?=[A-Za-z0-9+/]*[A-Z])"
                           rb"(?=[A-Za-z0-9+/]*[0-9])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/=])"),
}

# Public by structure, blanked before any rule runs.
STRUCTURAL_PUBLIC = [
    re.compile(rb"ENC\[age:[A-Za-z0-9+/=]+\]"),                                  # ciphertext (stage 33)
    re.compile(rb"\bgit@[A-Za-z0-9.-]+\.[A-Za-z]{2,}:"),                            # an scp-style git URL is not a person
    re.compile(rb"\bage1[a-z0-9]{58}\b"),                                        # age public key
    re.compile(rb"\b(?:h1|zh):[A-Za-z0-9+/=]{40,}"),                             # .terraform.lock.hcl hashes
    re.compile(rb"\b(?:ssh-(?:ed25519|rsa|dss)|ecdsa-sha2-nistp\d+|sk-[\w@.-]+)\s+[A-Za-z0-9+/]{40,}={0,3}"),
    re.compile(rb"\b(?:AAAAC3NzaC1lZDI1NTE5|AAAAB3NzaC1yc2E|AAAAE2VjZHNh)[A-Za-z0-9+/]{20,}={0,3}"),  # bare SSH public keys
]

_ZIP_MAGIC = b"PK\x03\x04"
_GZIP_MAGIC = b"\x1f\x8b"


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    excerpt: str          # the first characters only -- never the value

    def __str__(self) -> str:
        return f"{self.path}: {self.rule} ({self.excerpt})"


class PublicSafeError(ValueError):
    """Raised when material that must not be public would be written or committed."""

    def __init__(self, findings: Sequence[Finding], where: str = "") -> None:
        self.findings = list(findings)
        head = f"Refusing {where}: " if where else "Refusing: "
        super().__init__(head + "material that must not be public -- "
                         + "; ".join(str(f) for f in self.findings[:12])
                         + (f"; and {len(self.findings) - 12} more" if len(self.findings) > 12 else "")
                         + " (public-safe by construction; allow a value by decision in cfg/_config.yml public_safe.allow)")


def _excerpt(data: bytes, span: tuple[int, int]) -> str:
    text = data[span[0]:span[1]].decode("utf-8", "replace")
    return text[:6] + ("…" if len(text) > 6 else "")


def _allowed(text: bytes, allow: Sequence[str]) -> bool:
    low = text.lower()
    return any(a and not a.startswith("path:") and a.lower().encode() in low for a in allow)


def path_allowed(rel: str, allow: Sequence[str]) -> bool:
    """``path:<glob>`` entries accept a file whole (matched against the path
    and its basename)."""
    rel = rel.replace("\\", "/")
    name = Path(rel).name
    for a in allow:
        if a.startswith("path:"):
            pat = a[5:]
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat):
                return True
    return False


def scan_bytes(data: bytes, path: str, allow: Sequence[str] = (), *,
               hard_only: bool = False) -> list[Finding]:
    """Every finding in ``data`` (a compressed container is opened and its
    members scanned under ``<path>!<member>``)."""
    findings: list[Finding] = []
    if data[:4] == _ZIP_MAGIC:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    findings += scan_bytes(zf.read(info), f"{path}!{info.filename}", allow, hard_only=hard_only)
            return findings
        except zipfile.BadZipFile:
            pass
    if data[:2] == _GZIP_MAGIC:
        try:
            return scan_bytes(gzip.decompress(data), f"{path}!gunzip", allow, hard_only=hard_only)
        except (OSError, EOFError):
            pass
    cleaned = data
    for rx in STRUCTURAL_PUBLIC:
        cleaned = rx.sub(b"", cleaned)
    rules = dict(HARD_RULES)
    if not hard_only and not soft_exempt(path.split("!")[0]):
        rules.update(SOFT_RULES)
    for name, rule in rules.items():
        for span in rule(cleaned):
            if _allowed(cleaned[span[0]:span[1]], allow):
                continue
            findings.append(Finding(path, name, _excerpt(cleaned, span)))
    return findings


def scan_file(root: Path, rel: str, allow: Sequence[str] = (), data: bytes | None = None) -> list[Finding]:
    """One file: refused by name, accepted whole by decision, or scanned."""
    if path_allowed(rel, allow):
        return []
    if refused_path(rel):
        return [Finding(rel, "refused-path", Path(rel).name)]
    if data is None:
        p = root / rel
        if not p.is_file():
            return []
        data = p.read_bytes()
    return scan_bytes(data, rel, allow)


def git_toplevel(path: Path) -> Path | None:
    try:
        res = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=False)
    except OSError:
        return None
    return Path(res.stdout.strip()) if res.returncode == 0 and res.stdout.strip() else None


def candidate_files(root: Path) -> list[str]:
    """What a commit could publish: tracked files plus untracked files that
    are not ignored (``git ls-files -co --exclude-standard``); every file
    under ``root`` when it is not a git checkout."""
    top = git_toplevel(root)
    if top is not None:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
                             capture_output=True, check=True).stdout
        names = (p.decode() for p in out.split(b"\0") if p)
        return sorted(n for n in names if PRIVATE_DIRNAME not in Path(n).parts)
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")
                  if p.is_file() and ".git" not in p.parts and PRIVATE_DIRNAME not in p.parts)


def scan_tree(root: Path, allow: Sequence[str] = (), files: Iterable[str] | None = None) -> list[Finding]:
    root = Path(root)
    findings: list[Finding] = []
    for rel in (files if files is not None else candidate_files(root)):
        findings += scan_file(root, rel, allow)
    return findings


def staged_paths(top: Path, pathspecs: Sequence[str] = ()) -> list[str]:
    out = subprocess.run(["git", "-C", str(top), "diff", "--cached", "--name-only", "-z",
                          "--diff-filter=ACMR", "--", *pathspecs],
                         capture_output=True, check=True).stdout
    return sorted(p.decode() for p in out.split(b"\0") if p)


def scan_staged(top: Path, allow: Sequence[str] = (), pathspecs: Sequence[str] = ()) -> list[Finding]:
    """The index, as it would be committed: each staged blob read from git,
    not from the working tree."""
    findings: list[Finding] = []
    for rel in staged_paths(top, pathspecs):
        if path_allowed(rel, allow):
            continue
        if refused_path(rel):
            findings.append(Finding(rel, "refused-path", Path(rel).name))
            continue
        blob = subprocess.run(["git", "-C", str(top), "show", f":{rel}"], capture_output=True, check=True).stdout
        findings += scan_bytes(blob, rel, allow)
    return findings


def allow_from_config(config_yml: Path | None) -> list[str]:
    """``public_safe.allow`` read as text (the tree may not load without an
    identity; the gate must not depend on that)."""
    if config_yml is None or not Path(config_yml).is_file():
        return []
    doc = yaml.safe_load(Path(config_yml).read_text()) or {}
    section = doc.get("public_safe") or {}
    allow = section.get("allow") or []
    if not isinstance(allow, list) or not all(isinstance(a, str) for a in allow):
        raise ValueError(f"{config_yml}: public_safe.allow must be a list of strings")
    return allow


def config_for(root: Path) -> Path | None:
    """The configuration tree's ``cfg/_config.yml``; for the system repository,
    whose configuration is the frozen fixture, the fixture's."""
    for rel in (("cfg", "_config.yml"), ("tests", "fixtures", "config", "cfg", "_config.yml")):
        p = Path(root).joinpath(*rel)
        if p.is_file():
            return p
    return None


def assert_public_safe(data: Any, where: str = "meta-state") -> None:
    """Refuse to write ``data`` (a mapping about to become YAML) when it holds
    material a hard rule names -- the backstop on every meta-state and
    state-report write, unchanged in purpose since the first gate."""
    text = yaml.safe_dump(data, sort_keys=True, default_flow_style=False, allow_unicode=True).encode()
    findings = scan_bytes(text, where, hard_only=True)
    if findings:
        raise PublicSafeError(findings, where)


def format_findings(findings: Sequence[Finding]) -> str:
    return "\n".join(str(f) for f in findings)


# -------------------------------------------------- the plaintext set (49)

#: A plaintext shorter than this is not searched for: an initial, a two-letter
#: name or a short word matches the world, and the invariant test has always
#: skipped them for the same reason.
MIN_PLAINTEXT_LENGTH = 3


def _whole_token_matches(haystack: str, needle: str) -> bool:
    """``needle`` in ``haystack`` as a whole token: a last name is part of a
    public username, so a bare substring test would refuse the legitimate
    emission of a username derived from a name."""
    for m in re.finditer(re.escape(needle), haystack):
        before = haystack[m.start() - 1] if m.start() else " "
        after = haystack[m.end()] if m.end() < len(haystack) else " "
        if not (before.isalnum() or before in "_-.") and not (after.isalnum() or after in "_-."):
            return True
    return False


def scan_for_plaintexts(root: Path, plaintexts: Iterable[str],
                        subdirs: Sequence[str] = ("generated", "meta-state")) -> list[Finding]:
    """Every place a value the loader DECRYPTED appears in clear under
    ``subdirs`` (stage 49).

    This is the primary guard, and it does not guess: the system opened these
    markers itself, so it knows exactly what must not be in a committed file.
    The shape rules remain the backstop for material that was never a marker.
    """
    root = Path(root)
    wanted = sorted({p for p in plaintexts if len(p) >= MIN_PLAINTEXT_LENGTH})
    if not wanted:
        return []
    findings: list[Finding] = []
    for sub in subdirs:
        base = root / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or PRIVATE_DIRNAME in path.parts:
                continue
            try:
                text = path.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            rel = str(path.relative_to(root))
            for line_no, line in enumerate(text.splitlines(), 1):
                if any(_whole_token_matches(line, plain) for plain in wanted):
                    # the excerpt names the LINE, never the value
                    findings.append(Finding(path=f"{rel}:{line_no}",
                                            rule="decrypted-value-in-clear",
                                            excerpt="a value carried encrypted in the configuration "
                                                    "appears here in clear"))
                    break
    return findings


def assert_no_plaintext_emitted(root: Path, plaintexts: Iterable[str],
                                subdirs: Sequence[str] = ("generated", "meta-state")) -> None:
    findings = scan_for_plaintexts(root, plaintexts, subdirs)
    if findings:
        raise PublicSafeError(findings, "the emission")
