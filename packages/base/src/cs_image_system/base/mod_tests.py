# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Local modification tests (EXPLORE "Automated Testing for Modifications").

Every modification of an instance image is run against a throwaway LOCAL
target matching the image's OS family -- a container -- twice:

1. the first run must exit 0 (the mod applies cleanly);
2. the second run must change nothing (idempotence): the target's
   filesystem diff after run two equals the diff after run one.

The harness is plugin-shaped: the target is an abstract ``LocalTarget``
(a ``docker`` implementation ships; tests use a fake), the OS plugin says
which container image stands in for a family/version, and each mod
builder's ``local_test`` runs its kind of modification on the target.
Results are recorded in ``meta-state/mod-tests.yaml`` keyed by the mod's
content hash, so an unchanged mod is not re-tested; nothing here touches a
cloud.
"""
from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import asdict, field
from .models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from .lineage import mod_records

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext

log = logging.getLogger(__name__)

MOD_TESTS_FILE = "mod-tests.yaml"

# Family/version -> container image standing in for the OS (overridable per
# OS builder through ``local_test_image``).
DEFAULT_TEST_IMAGES: dict[str, str] = {
    "rhel": "rockylinux:{version}",
    "rocky-linux": "rockylinux:{version}",
    "alma-linux": "almalinux:{version}",
    "centos": "quay.io/centos/centos:stream{version}",
    "debian": "debian:{version}",
    "ubuntu": "ubuntu:{version}",
    "fedora": "fedora:{version}",
}

# Ansible modules need a Python the controller's ansible-core supports; bare
# OS containers have none, and RHEL-8-era images ship 3.6. Install the newest
# python3.x the family offers, then point ansible at it.
ANSIBLE_PREP = (
    "for v in 3.12 3.11 3.9; do command -v python$v >/dev/null 2>&1 && exit 0; "
    "(command -v dnf >/dev/null 2>&1 && dnf -y install python$v >/dev/null 2>&1) && exit 0; done; "
    "command -v python3 >/dev/null 2>&1 || (command -v dnf >/dev/null 2>&1 && dnf -y install python3) || "
    "(command -v yum >/dev/null 2>&1 && yum -y install python3) || "
    "(apt-get update && apt-get install -y python3)")
ANSIBLE_INTERPRETER = "ls /usr/bin/python3.[0-9]* 2>/dev/null | grep -v config | sort -V | tail -1 || echo /usr/bin/python3"

# A sudo shim for containers running as root without sudo installed. It
# skips sudo's own options (ansible's become uses `sudo -H -S -n -u root`)
# and execs the command as the current (root) user.
SUDO_SHIM = r"""command -v sudo >/dev/null 2>&1 || { cat > /usr/local/bin/sudo <<'CSIS_SUDO'
#!/bin/sh
while [ $# -gt 0 ]; do
  case "$1" in
    -u|-g|-p|-C|-r|-t|-U|-h) shift 2 ;;
    --) shift; break ;;
    -*) shift ;;
    *) break ;;
  esac
done
exec "$@"
CSIS_SUDO
chmod 0755 /usr/local/bin/sudo; }"""


class LocalTarget(Protocol):
    """A throwaway machine the harness can drive."""
    name: str

    def exec(self, command: str) -> tuple[int, str]: ...
    def copy_in(self, source: Path, dest: str) -> None: ...
    def diff(self) -> list[str]: ...
    def close(self) -> None: ...


class DockerTarget:
    """A ``docker run -d`` container kept alive with ``sleep infinity``."""

    def __init__(self, image: str, docker: str = "docker") -> None:
        self.docker = docker
        self.image = image
        self.name = subprocess.run(
            [docker, "run", "-d", "--rm", image, "sh", "-c", "sleep infinity"],
            check=True, capture_output=True, text=True).stdout.strip()

    def exec(self, command: str) -> tuple[int, str]:
        res = subprocess.run([self.docker, "exec", self.name, "sh", "-c", command],
                             capture_output=True, text=True, check=False)
        return res.returncode, (res.stdout or "") + (res.stderr or "")

    def copy_in(self, source: Path, dest: str) -> None:
        subprocess.run([self.docker, "cp", str(source), f"{self.name}:{dest}"], check=True,
                       capture_output=True, text=True)

    def diff(self) -> list[str]:
        res = subprocess.run([self.docker, "diff", self.name], capture_output=True, text=True, check=True)
        return sorted(l for l in res.stdout.splitlines() if l.strip())

    def close(self) -> None:
        subprocess.run([self.docker, "rm", "-f", self.name], capture_output=True, text=True, check=False)


def docker_available(docker: str = "docker") -> bool:
    if shutil.which(docker) is None:
        return False
    return subprocess.run([docker, "info"], capture_output=True, text=True, check=False).returncode == 0


@dataclass(config=CSIS_MODEL_CONFIG)
class ModTestResult:
    image: str
    mod: str
    type: str
    content_hash: str
    target: str
    status: str                       # pass | fail | skipped | unsupported
    idempotent: bool | None = None
    first_run_rc: int | None = None
    second_run_rc: int | None = None
    changes_on_rerun: list[str] = field(default_factory=list)
    detail: str = ""
    run: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------- plugin side

def test_image_for(ctx: "GlobalTypeContext", image: Any) -> str | None:
    """The container image for the instance image's root OS family."""
    from .capabilities import image_chain
    _, root = image_chain(ctx, image)
    osb = ctx.os_builders.get(root) if root else None
    if osb is None:
        return None
    override = getattr(osb.model, "local_test_image", None)
    if override:
        return str(override)
    fam = str(osb.get_family()).lower()
    version = osb.get_family_version()
    if fam == "rhel" and str(version).isdigit() and int(version) >= 10:
        # Docker Hub's `rockylinux` library stops at 9 (found 2026-09-10 by the
        # first `full-test`); from 10 the stand-in is AlmaLinux -- which is
        # what the AWS chain bakes since stage 13
        return f"almalinux:{version}"
    tmpl = DEFAULT_TEST_IMAGES.get(fam)
    return tmpl.format(version=version) if tmpl else None


def _inline_lines(mod: Any) -> list[str]:
    """ensure-generated guarded lines (bash items) + free-form script lines."""
    out: list[str] = []
    ensure_fn = getattr(mod, "ensure_lines", None)
    if callable(ensure_fn):
        out.extend(str(l) for l in cast_list(ensure_fn()))
    out.extend(str(l) for l in (getattr(mod, "script", None) or []))
    return out


def cast_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def bash_test_commands(mod: Any, staged: Path) -> list[str]:
    """Commands that apply a bash mod inside the target, from its staged copy."""
    cmds: list[str] = []
    for sf in list(getattr(mod, "scripts", None) or []):
        cmds.append(f"sh {shlex.quote('/tmp/csis-test/' + Path(str(sf)).name)}")
    if _inline_lines(mod):
        cmds.append("sh /tmp/csis-test/inline.sh")
    return cmds


def _stage_mod(ctx: "GlobalTypeContext", mod: Any) -> Path:
    """Copy a mod's files to a temp dir (the container gets /tmp/csis-test)."""
    d = Path(tempfile.mkdtemp(prefix="csis-mod-test-"))
    for src in list(getattr(mod, "playbooks", None) or []) + list(getattr(mod, "scripts", None) or []):
        p = Path(str(src))
        candidates = [p] if p.is_absolute() else [Path(ctx.working_path) / p, p]
        found = next((c for c in candidates if c.is_file()), None)
        if found is not None:
            shutil.copy2(found, d / found.name)
    lines = _inline_lines(mod)
    if lines:
        (d / "inline.sh").write_text("#!/bin/sh\nset -eu\n" + "\n".join(lines) + "\n")
    return d


def apply_mod(ctx: "GlobalTypeContext", mod: Any, target: LocalTarget, staged: Path) -> tuple[int, str]:
    """Apply one modification to the target once. Ansible mods run through
    the docker connection when the target is a container; bash mods exec."""
    playbooks = list(getattr(mod, "playbooks", None) or [])
    if playbooks:
        rc_total, out_total = 0, ""
        _, interp = target.exec(ANSIBLE_INTERPRETER)
        interp = (interp.strip().splitlines() or ["/usr/bin/python3"])[-1].strip() or "/usr/bin/python3"
        for pb in playbooks:
            cmd = ["ansible-playbook", "-i", f"{target.name},", "-c", "docker",
                   "-e", f"ansible_python_interpreter={interp}", str(staged / Path(str(pb)).name)]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            rc_total = rc_total or res.returncode
            out_total += res.stdout + res.stderr
        return rc_total, out_total
    target.exec("rm -rf /tmp/csis-test && mkdir -p /tmp/csis-test")
    target.copy_in(staged, "/tmp/csis-test-src")
    target.exec("cp -r /tmp/csis-test-src/. /tmp/csis-test/ && rm -rf /tmp/csis-test-src")
    rc_total, out_total = 0, ""
    for c in bash_test_commands(mod, staged):
        rc, out = target.exec(c)
        out_total += out
        if rc != 0:
            return rc, out_total
    return rc_total, out_total


def _volatile(path_line: str) -> bool:
    """docker diff entries that change on any command and mean nothing."""
    p = path_line[2:] if len(path_line) > 2 else path_line
    return p.startswith(("/tmp", "/var/log", "/var/cache", "/var/lib/dnf", "/var/lib/rpm/__db",
                         "/root/.ansible", "/root/.cache", "/var/lib/apt/lists", "/run"))


def test_mod(ctx: "GlobalTypeContext", image: Any, mod: Any, record: dict[str, Any],
             target: LocalTarget) -> ModTestResult:
    result = ModTestResult(image=image.get_name(), mod=mod.get_name(), type=mod.get_type(),
                           content_hash=record["content_hash"], target=target.name, status="fail",
                           run=ctx.run_id)
    staged = _stage_mod(ctx, mod)
    try:
        target.exec(SUDO_SHIM)
        if getattr(mod, "playbooks", None):
            rc0, out0 = target.exec(ANSIBLE_PREP)
            if rc0 != 0:
                result.status = "fail"
                result.detail = "target preparation for ansible failed: " + out0[-1500:]
                return result
        rc1, out1 = apply_mod(ctx, mod, target, staged)
        result.first_run_rc = rc1
        if rc1 != 0:
            result.detail = out1[-2000:]
            return result
        before = {l for l in target.diff() if not _volatile(l)}
        rc2, out2 = apply_mod(ctx, mod, target, staged)
        result.second_run_rc = rc2
        after = {l for l in target.diff() if not _volatile(l)}
        result.changes_on_rerun = sorted(after - before)
        result.idempotent = rc2 == 0 and not result.changes_on_rerun
        if "changed=" in out2:   # ansible recap adds its own verdict
            changed = [seg for seg in out2.split() if seg.startswith("changed=")]
            if any(seg != "changed=0" for seg in changed):
                result.idempotent = False
                result.detail = "ansible reported changes on the second run"
        result.status = "pass" if rc2 == 0 else "fail"
        if rc2 != 0:
            result.detail = out2[-2000:]
        return result
    finally:
        shutil.rmtree(staged, ignore_errors=True)


def run_mod_tests(ctx: "GlobalTypeContext", images: list[str] | None = None,
                  make_target=None, force: bool = False) -> list[ModTestResult]:
    """Test every modification of every (selected) instance image. Results
    keyed by content hash are cached in meta-state; ``force`` re-tests."""
    ms = ctx.meta_state
    previous = ms.read(MOD_TESTS_FILE).setdefault("results", {})
    results: list[ModTestResult] = []
    for image in ctx.images:
        if images and image.get_name() not in images:
            continue
        mods = [m for m in (getattr(image, "modifications", None) or []) if not isinstance(m, dict)]
        if not mods:
            continue
        records = mod_records(ctx, image)
        container_image = test_image_for(ctx, image)
        if container_image is None:
            for mod, rec in zip(mods, records):
                results.append(ModTestResult(image=image.get_name(), mod=mod.get_name(), type=mod.get_type(),
                                             content_hash=rec["content_hash"], target="", status="unsupported",
                                             detail="no local test image for the root OS family", run=ctx.run_id))
            continue
        if make_target is None:
            if not docker_available():
                for mod, rec in zip(mods, records):
                    results.append(ModTestResult(image=image.get_name(), mod=mod.get_name(), type=mod.get_type(),
                                                 content_hash=rec["content_hash"], target=container_image,
                                                 status="skipped", detail="docker is not available", run=ctx.run_id))
                continue
            make_target = DockerTarget
        pending = [(m, r) for m, r in zip(mods, records)
                   if force or previous.get(r["content_hash"], {}).get("status") != "pass"]
        for mod, rec in zip(mods, records):
            if (mod, rec) not in pending:
                cached = dict(previous[rec["content_hash"]])
                cached["detail"] = "cached: unchanged since last pass"
                results.append(ModTestResult(**{k: v for k, v in cached.items() if k in ModTestResult.__dataclass_fields__}))
        if not pending:
            continue
        target = make_target(container_image)
        try:
            for mod, rec in pending:
                r = test_mod(ctx, image, mod, rec, target)
                results.append(r)
                previous[rec["content_hash"]] = r.to_dict()
        finally:
            target.close()
    ms.write(MOD_TESTS_FILE, {"results": previous})
    return results
