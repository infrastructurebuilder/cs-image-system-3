# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 86: a bake waits for the package database.

Found walking the daily driver (stage 65, findings F28 and F29). The account's
Systems Manager acts on every new machine -- agent updates, a patch scan,
inventory -- and held the package database while packer provisioned: `rpm`
gave up at once ("can't create transaction lock") and the base bake with it,
twice. So the first provisioner of every bake settles the machine and writes
a step runner, and every package step the system emits runs through it: a
step that fails on a held database is run again, any other failure fails at
once. And the three `standard-*` starters tested their base image for `git`,
which no base carries.

The runner and the settle are exercised here as the shell they emit, with
stand-ins for the machine; the same shell against a really held rpm and dpkg
lock is `tests/test_v2_bake_steps_containers.py` (a leg of `just full-test`).
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

from cs_image_system.base import bake_steps
from tests.v2_support import V2Run, copy_config, load_context, stub_environment

REPO = Path(__file__).resolve().parent.parent
RPM_BUSY = "error: can't create transaction lock on /usr/lib/sysimage/rpm/.rpm.lock (Resource temporarily unavailable)"
DPKG_BUSY = "dpkg: error: dpkg frontend lock was locked by another process with pid 13"
APT_BUSY = "E: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process 4242 (apt-get)"


# ------------------------------------------------------------ the step runner

def _runner(tmp_path: Path) -> Path:
    path = tmp_path / "csis-step"
    path.write_text("\n".join(bake_steps.step_runner_lines()) + "\n")
    return path


def _step(tmp_path: Path, body: str) -> Path:
    """A step the way packer writes an inline one: `/bin/sh -e`, executable."""
    path = tmp_path / "step.sh"
    path.write_text("#!/bin/sh -e\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _run(runner: Path, step: Path, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sh", str(runner), str(step)], capture_output=True, text=True, timeout=60,
                          env={**os.environ, "CSIS_STEP_WAIT": "0", **env})


@pytest.mark.parametrize("said", [RPM_BUSY, DPKG_BUSY, APT_BUSY])
def test_a_step_that_meets_a_held_package_database_is_run_again(tmp_path: Path, said: str):
    """The walk's failure: busy twice, then free. The step passes on its third
    run, and the log says why it ran three times."""
    count = tmp_path / "count"
    step = _step(tmp_path, f'n=$(cat {count} 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > {count}\n'
                           f'if [ "$n" -lt 3 ]; then echo "{said}" >&2; exit 1; fi\necho imported\n')
    done = _run(_runner(tmp_path), step)
    assert done.returncode == 0, done.stdout + done.stderr
    assert count.read_text().strip() == "3"
    assert done.stdout.count("the package database was held by another process") == 2
    assert "attempt 1 of 10" in done.stdout and "imported" in done.stdout


def test_a_step_that_fails_for_another_reason_fails_at_once(tmp_path: Path):
    """The walk's OTHER failure (F28) must stay what it was: one run, its own
    exit status, no waiting."""
    count = tmp_path / "count"
    step = _step(tmp_path, f'echo x >> {count}\necho "package git is not installed" >&2\nexit 7\n')
    done = _run(_runner(tmp_path), step)
    assert done.returncode == 7
    assert count.read_text().count("x") == 1
    assert "held by another process" not in done.stdout
    assert "package git is not installed" in done.stdout, "the step's own words still reach the log"


def test_a_database_that_never_comes_free_stops_the_step_after_its_tries(tmp_path: Path):
    count = tmp_path / "count"
    step = _step(tmp_path, f'echo x >> {count}\necho "{RPM_BUSY}" >&2\nexit 1\n')
    done = _run(_runner(tmp_path), step, CSIS_STEP_TRIES="3")
    assert done.returncode == 1
    assert count.read_text().count("x") == 3, "three runs in all, not three more"
    assert done.stdout.count("held by another process") == 2


def test_a_passing_step_runs_once_and_keeps_its_environment(tmp_path: Path):
    count = tmp_path / "count"
    step = _step(tmp_path, f'echo x >> {count}\necho "value=$PACKER_SAYS"\n')
    done = _run(_runner(tmp_path), step, PACKER_SAYS="hello")
    assert done.returncode == 0 and "value=hello" in done.stdout
    assert count.read_text().count("x") == 1


def test_the_execute_command_runs_through_the_runner_only_where_one_exists(tmp_path: Path):
    """packer's default command with the runner in front; a machine without
    one (it rebooted mid-bake and lost /run) runs the step as before."""
    step = _step(tmp_path, 'echo "ran with $WHO"\n')
    runner = _runner(tmp_path)
    command = bake_steps.EXECUTE_COMMAND.replace("{{ .Path }}", str(step)).replace("{{ .Vars }}", "WHO=packer")
    assert bake_steps.STEP_RUNNER in command and "{{" not in command
    with_runner = subprocess.run(["sh", "-c", command.replace(bake_steps.STEP_RUNNER, str(runner))],
                                 capture_output=True, text=True, timeout=30)
    without = subprocess.run(["sh", "-c", command.replace(bake_steps.STEP_RUNNER, str(tmp_path / "absent"))],
                             capture_output=True, text=True, timeout=30)
    for done in (with_runner, without):
        assert done.returncode == 0 and "ran with packer" in done.stdout, done.stdout + done.stderr


def test_the_settle_writes_the_runner_it_describes(tmp_path: Path):
    """The settle's own lines, run as a script: what lands at the runner's
    path is the runner, byte for byte (the heredoc expands nothing)."""
    target = tmp_path / "run" / "csis-step"
    target.parent.mkdir()
    bin_dir = _shims(tmp_path, {"sudo": 'exec "$@"\n', "cloud-init": "exit 0\n", "timeout": 'shift; exec "$@"\n'})
    script = "\n".join(bake_steps.settle_commands([])).replace(bake_steps.STEP_RUNNER, str(target))
    done = subprocess.run(["sh", "-e", "-c", script], capture_output=True, text=True, timeout=30,
                          env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"})
    assert done.returncode == 0, done.stderr
    assert target.read_text() == "\n".join(bake_steps.step_runner_lines()) + "\n"


# --------------------------------------------- the AWS runtime's fleet wait

def _shims(tmp_path: Path, scripts: dict[str, str]) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in scripts.items():
        path = bin_dir / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
    return bin_dir


def _aws_settle(tmp_path: Path, monkeypatch) -> list[str]:
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path), dry_run=True)
    rtb = ctx.runtime_builders["aws-east2-runtime"]
    return rtb.bake_settle_commands("rhel")


def _run_settle(tmp_path: Path, commands: list[str], *, uptime: str, worker_leaves_after: int | None,
                worker: str = "/usr/bin/ssm-document-worker\0abc-123\0") -> tuple[subprocess.CompletedProcess[str], int]:
    """The emitted loop against a stand-in /proc. `sleep` is a shim that counts
    its calls and takes the worker away after `worker_leaves_after` of them."""
    proc = tmp_path / "proc"
    (proc / "4242").mkdir(parents=True)
    (proc / "uptime").write_text(uptime)
    (proc / "1").mkdir()
    (proc / "1" / "cmdline").write_bytes(b"/usr/lib/systemd/systemd\0")
    if worker_leaves_after is not None:
        (proc / "4242" / "cmdline").write_bytes(worker.encode())
    sleeps = tmp_path / "sleeps"
    gone = "9999" if worker_leaves_after is None else str(worker_leaves_after)
    bin_dir = _shims(tmp_path, {
        "sudo": 'exec "$@"\n',
        "sleep": f'echo x >> {sleeps}\n[ "$(wc -l < {sleeps})" -ge {gone} ] && rm -f {proc}/4242/cmdline\nexit 0\n',
    })
    script = "\n".join(commands).replace("/proc/", f"{proc}/")
    done = subprocess.run(["sh", "-e", "-c", script], capture_output=True, text=True, timeout=60,
                          env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"})
    return done, (sleeps.read_text().count("x") if sleeps.is_file() else 0)


def test_the_aws_settle_waits_while_systems_manager_runs_a_document(tmp_path: Path, monkeypatch):
    """A document worker is on the machine for five checks, then gone: the
    bake goes on three quiet checks later, and says how long it waited."""
    done, sleeps = _run_settle(tmp_path, _aws_settle(tmp_path, monkeypatch), uptime="200.00 150.00\n",
                               worker_leaves_after=5)
    assert done.returncode == 0, done.stderr
    assert sleeps == 8, "five busy checks, then three quiet ones"
    assert "Systems Manager is quiet on this machine (waited 80 seconds)" in done.stdout


def test_the_aws_settle_sees_the_agents_own_updater_too(tmp_path: Path, monkeypatch):
    done, sleeps = _run_settle(tmp_path, _aws_settle(tmp_path, monkeypatch), uptime="200.00 150.00\n",
                               worker_leaves_after=2,
                               worker="/var/lib/amazon/ssm/update/amazon-ssm-agent-updater/3.3.1/updater\0-update\0")
    assert done.returncode == 0 and sleeps == 5, done.stdout + done.stderr


def test_the_aws_settle_does_not_judge_a_machine_that_only_just_booted(tmp_path: Path, monkeypatch):
    """The associations start about forty seconds after launch: a machine
    younger than the minimum age is never called quiet. (The stand-in clock
    does not move, so the wait runs to its bound and says so.)"""
    done, sleeps = _run_settle(tmp_path, _aws_settle(tmp_path, monkeypatch), uptime="20.00 5.00\n",
                               worker_leaves_after=None)
    assert done.returncode == 0, done.stderr
    assert sleeps == 60, "the whole bound, ten seconds at a time"
    assert "was still acting on this machine after 600 seconds; going on" in done.stdout


def test_the_aws_settle_is_short_on_a_quiet_machine_and_does_not_find_itself(tmp_path: Path, monkeypatch):
    """No worker, old enough: three checks. The search's own command line
    carries the pattern and must not count as a worker."""
    commands = _aws_settle(tmp_path, monkeypatch)
    done, sleeps = _run_settle(tmp_path, commands, uptime="200.00 150.00\n", worker_leaves_after=None)
    assert done.returncode == 0 and sleeps == 3, done.stdout + done.stderr
    pattern = re.search(r"grep -Eaqs '([^']+)'", "\n".join(commands))
    assert pattern, "the loop searches the process list"
    assert not re.search(pattern.group(1), "\n".join(commands)), "the pattern does not match its own text"


def test_a_runtime_without_session_manager_adds_no_wait():
    from cs_image_system.base.basic.builder_base_runtime import RuntimeBuilderBase
    assert RuntimeBuilderBase.bake_settle_commands.__doc__
    assert RuntimeBuilderBase.bake_settle_commands(object(), "rhel") == []        # type: ignore[arg-type]


# ------------------------------------------------------------- the emission

@pytest.fixture
def builds(tmp_path: Path, monkeypatch) -> dict[str, str]:
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run(["base-image", "instance-image"], apply=False).ok
        return {str(p.relative_to(run.generated)): p.read_text() for p in run.generated.rglob("*-build.pkr.hcl")}
    finally:
        run.restore_cwd()


def _provisioners(text: str) -> list[tuple[str, str]]:
    """(comment, block) for every shell provisioner, in order."""
    found = []
    for m in re.finditer(r'^[ \t]*provisioner "shell" \{\n(.*?)^[ \t]*\}\n', text, re.S | re.M):
        before = text[:m.start()].rstrip("\n").splitlines()
        comment = before[-1].strip() if before and before[-1].strip().startswith("#") else ""
        found.append((comment, m.group(1)))
    return found


def test_every_bake_settles_before_anything_else(builds: dict[str, str]):
    """For EVERY image of every build block, base and instance alike and on
    both clouds, the first provisioner that names it is the settle."""
    assert len(builds) >= 5
    for path, text in builds.items():
        first: dict[str, str] = {}
        for comment, block in _provisioners(text):
            only = re.search(r'only\s*=\s*\["([^"]+)"\]', block)
            assert only, f"{path}: a provisioner with no source"
            first.setdefault(only.group(1), comment)
        sources = re.findall(r'"source\.([^"]+)"', text)
        assert sources and set(sources) == set(first), f"{path}: every source has provisioners"
        for source, comment in first.items():
            assert comment.startswith("# before anything else: the build machine settles"), f"{path}: {source}: {comment}"


def test_the_settle_writes_the_runner_and_does_not_use_it(builds: dict[str, str]):
    for path, text in builds.items():
        settles = [b for c, b in _provisioners(text) if "the build machine settles" in c]
        assert settles, path
        for block in settles:
            assert "execute_command" not in block, f"{path}: the runner does not exist yet when the settle runs"
            assert f"sudo tee {bake_steps.STEP_RUNNER} >/dev/null <<'CSIS_STEP'" in block
            assert "cloud-init status --wait" in block


def test_the_aws_bakes_wait_for_systems_manager_and_the_gce_ones_do_not(builds: dict[str, str]):
    aws = "".join(t for p, t in builds.items() if "pckr-ebs-ans" in p)
    gce = "".join(t for p, t in builds.items() if "pckr-gce-ans" in p)
    assert aws and gce
    assert "Systems Manager may act on every new machine" in aws and "ssm-document-work[e]r" in aws
    assert "Systems Manager" not in gce and "ssm-document" not in gce


def test_every_package_step_the_system_emits_runs_through_the_runner(builds: dict[str, str]):
    """The OS update, the identity and storage prerequisites, the session
    agent, the ansible builder's python and a bash modification: each block
    carries the execute command. Verification and finalization read the
    package database, never write it, and are left as they were."""
    line = bake_steps.execute_command_line("").strip()
    seen: set[str] = set()
    for path, text in builds.items():
        for comment, block in _provisioners(text):
            packages = re.search(r"\b(dnf|yum|apt-get|rpm --import|zypper)\b", block)
            if "the build machine settles" in comment or "in-bake verification" in comment \
                    or "runtime bake finalization" in comment:
                assert "execute_command" not in block, f"{path}: {comment}"
                continue
            if packages:
                assert line in block, f"{path}: a package step outside the runner: {comment or block[:120]}"
                seen.add(comment.split("(")[0].split("'")[0].strip("# ").split(" for ")[0])
    assert {"OS update", "identity type", "debug session mechanism"} <= seen, seen


def test_a_bash_builder_that_says_how_its_script_runs_keeps_its_own_command(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    path = root / "cfg" / "mod-builders.yml"
    data = yaml.safe_load(path.read_text())
    next(b for b in data["mod_builders"] if b["name"] == "bash-remote")["configuration_user"] = "modder"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["base-image", "instance-image"], apply=False).ok
        text = "".join(p.read_text() for p in run.generated.rglob("*-build.pkr.hcl") if "instance-image" in str(p))
    finally:
        run.restore_cwd()
    own = [b for _, b in _provisioners(text) if "sudo su - modder -c" in b]
    assert own, "the builder's command is still emitted"
    assert all(bake_steps.STEP_RUNNER not in b for b in own), "and nothing is put in front of it"


def test_an_image_fingerprint_does_not_see_how_its_steps_run(tmp_path: Path, monkeypatch):
    """The settle and the runner are execution detail, not content: taking this
    release must not make every standing image due. A runtime that settles
    differently, and a runner with other bounds, leave every fingerprint
    where it was. (The golden pins the same thing from the other side: its
    packer sources, which carry the fingerprint, did not move.)"""
    from cs_image_system.base.lineage import input_fingerprint
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path), dry_run=True)
    images = list(ctx.base_images) + list(ctx.images_map.values())
    assert len(images) >= 5
    before = {i.get_name(): input_fingerprint(ctx, i) for i in images}
    for rtb in ctx.runtime_builders.values():
        monkeypatch.setattr(type(rtb), "bake_settle_commands", lambda self, family=None: ["sleep 3600"])
    monkeypatch.setattr(bake_steps, "STEP_TRIES", 99)
    monkeypatch.setattr(bake_steps, "EXECUTE_COMMAND", "something else entirely")
    assert {i.get_name(): input_fingerprint(ctx, i) for i in images} == before


# ------------------------------------------------------------- the starters

STARTER_BASE_PACKAGES = {
    "standard-aws": ["scaleft-server-tools"],        # what `identity_types: [okta]` bakes in
    "standard-aws-posix": ["amazon-ssm-agent"],      # what `session_mechanism: ssm` bakes in
    "standard-gce": ["google-guest-agent"],          # what the vendor's GCE image ships
}


@pytest.mark.parametrize("starter", sorted(STARTER_BASE_PACKAGES))
def test_a_starters_base_test_names_only_what_a_base_carries(starter: str):
    """F28: the three starters asserted `git` on the base. A base takes no
    modifications and the vendor image has no git, so the first base bake of
    any tree made from them failed its own test; git is the IMAGE's, where
    the playbook installs it and the image's test checks it."""
    root = REPO / "docs" / "examples" / starter
    builders = yaml.safe_load((root / "cfg" / "os-builders.yml").read_text())["os_builders"]
    assert len(builders) == 1
    assert builders[0]["tests"]["packages"] == STARTER_BASE_PACKAGES[starter]
    playbook_packages = set(re.findall(r"\b(git|python3|tmux)\b", "".join(
        p.read_text() for p in (root / "playbooks").glob("*.yml")) if (root / "playbooks").is_dir() else ""))
    assert not playbook_packages & set(builders[0]["tests"]["packages"]), \
        "a base test names a package only the image's playbook installs"


@pytest.mark.parametrize("starter", ["standard-aws", "standard-aws-posix"])
def test_the_base_bake_itself_installs_what_the_starters_base_test_asserts(starter: str, tmp_path: Path, monkeypatch):
    """Not a list in a test alone: the emitted base bake of the starter has a
    step that installs the package its verification then asks for."""
    from tests.test_docs_examples import copy_example, stub_networks_from, stub_opa_credentials_from
    from tests.v2_support import run_v2
    stub_environment(monkeypatch)
    root = copy_example(tmp_path, starter)
    stub_networks_from(monkeypatch, root)
    stub_opa_credentials_from(monkeypatch, root)
    cwd = os.getcwd()
    try:
        load_context(root, dry_run=True)
        assert run_v2(["base-image"], apply=False).ok
        text = "".join(p.read_text() for p in (root / "generated").rglob("*-build.pkr.hcl") if "base-image" in str(p))
    finally:
        os.chdir(cwd)
    package = STARTER_BASE_PACKAGES[starter][0]
    blocks = _provisioners(text)
    verify = [b for c, b in blocks if "in-bake verification" in c]
    installs = [b for c, b in blocks if "in-bake verification" not in c and re.search(r"\b(yum|dnf) install\b", b)]
    assert verify and f"rpm -q {package}" in verify[0], "the verification asks for the package"
    assert any(package in b for b in installs), f"no step of the base bake installs {package}"
