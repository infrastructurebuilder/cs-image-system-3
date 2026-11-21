# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Shared harness for the tests that run the meta-workflow with every
provider installed.

Every such test runs the real pipeline over a private COPY of the frozen
fixture (``tests/fixtures/config``: owned by the tests, never a
live configuration) with all external touchpoints stubbed:

* no cloud: AWS networking discovery and vendor-AMI queries are
  replaced; nothing in these tests can read or write AWS/Okta;
* no tools: ``ExecutableModel.execute`` is journaled, never run;
* deterministic: the run timestamp and ``USER`` are pinned, and dummy okta /
  oktapam credentials are present so command lists never depend on the
  developer's shell.

The harness is a composition. What names no provider is the published test
kit (``cs_image_system.system.testing``), which a provider's own suite uses
directly. What stands in for a provider is that provider's own stub
function where its package ships one (docker, the terraform roots library);
the stubs for AWS and Okta are kept here, beside the frozen
fixture that declares all of them.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from cs_image_system.docker_runtime import testing as docker_testing
from cs_image_system.hashicorp_utils.testing import BareRun, bare_run
from cs_image_system.system import testing as kit
from cs_image_system.system.testing import (
    FIXED_CHECKED_AT,
    FIXED_NOW,
    FIXED_RUN_ID,
    FIXED_TIMESTAMP,
    cli_context,
    command_lines,
    drive_lifecycles,
    load_context,
    module_path,
    modules_beside,
    modules_inside,
    os_type_for_family,
    passing_session,
    tree,
)
from cs_image_system.tofu_roots import testing as roots_testing

__all__ = [
    "DOCKER_DIGEST",
    "FIXED_CHECKED_AT",
    "FIXED_NOW",
    "FIXED_RUN_ID",
    "FIXED_TIMESTAMP",
    "FIXTURE_CONFIG",
    "REPO",
    "VENDOR_AMI",
    "VPCS",
    "BareRun",
    "FixtureRun",
    "bare_run",
    "cli_context",
    "command_lines",
    "copy_config",
    "docker_binary",
    "drive_lifecycles",
    "load_context",
    "module_path",
    "modules_beside",
    "modules_inside",
    "os_type_for_family",
    "plain",
    "record_network_facts",
    "stub_environment",
    "tree",
]

REPO = Path(__file__).resolve().parents[1]
FIXTURE_CONFIG = REPO / "tests" / "fixtures" / "config"     # frozen; the live tree is elsewhere

VPCS = ["vpc-0c78d0d63b7a100df", "vpc-0381e9f82c9ae68e7", "default"]
VENDOR_AMI = "ami-0feedfacecafebeef"
# what the fixture's docker runtime (docker-fixture) "pulls" -- a digest reference no registry holds
DOCKER_DIGEST = docker_testing.DIGEST


class _AnySecurityGroups(dict):
    """Stubbed account SG map: membership always true. Which security groups
    exist is a live-account fact; the fixture's configured ids are data, not
    values these tests should restate."""
    def __contains__(self, key: object) -> bool:
        return True


def copy_config(tmp_path: Path, name: str = "config") -> Path:
    """A private copy of the frozen fixture (without any generated output).
    The transient apply_* flags are normalized to false -- a live run's
    TEMP flag flip must never leak into tests (found live, when the fixture
    was still the live tree); tests that want a flag on set ``ctx.config``
    (and the file, for apply-check) themselves. Copies start non-ephemeral
    (rule 58) and tests that want it declare it."""
    dst = kit.copy_fixture(FIXTURE_CONFIG, tmp_path, name)
    # The suite's instance subjects (test, test2, container-test) are declared in
    # the fixture itself; nothing is injected here.
    # The one meta-state file a copy starts with: the network
    # facts record a real run would have written, saying exactly what the
    # harness's cloud stubs answer, so an offline load adopts the same
    # networks the stubs used to resolve at load and the emission stays put.
    record_network_facts(dst)
    return dst


def record_network_facts(root: Path, checked_at: str = FIXED_CHECKED_AT) -> Path:
    """Write ``<root>/meta-state/runtime-facts.yaml`` for the tree under
    ``root``, derived from its own ``cfg/*.yml`` (the ids are the tree's
    data, not literals restated here): every aws runtime's declared
    network (a `default` recorded as the literal ``default``, what the
    harness's stubs answer as the account's default), its declared subnet
    ids and its declared security groups -- as if a real run had
    checked them. The path is returned."""
    import yaml as _yaml

    from cs_image_system.contract.constants import OOPS_DEFAULTS
    runtimes: dict[str, dict] = {}
    for p in sorted((root / "cfg").glob("*.y*ml")):
        doc = _yaml.safe_load(p.read_text()) or {}
        for r in (doc.get("runtime_builders") or []) if isinstance(doc, dict) else []:
            if not isinstance(r, dict) or r.get("type") != "aws" or not r.get("name"):
                continue
            net = r.get("networking") or {}
            network = net.get("network")
            facts: dict = {"network": "default" if network in OOPS_DEFAULTS else str(network),
                           "subnets": [str(s.get("subnet_id")) for s in net.get("subnets") or []],
                           "security_groups": [str(sg) for sg in net.get("addl_security_groups") or []]}
            facts["checked_at"] = checked_at
            runtimes[str(r["name"])] = facts
    path = root / "meta-state" / "runtime-facts.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_yaml.safe_dump({"runtimes": runtimes}, sort_keys=True, default_flow_style=False))
    return path


def docker_binary() -> str:
    """The docker CLI the FIXTURE declares (``cfg/executables.yml``, entry
    ``docker``) when its binary exists on this machine, else ``docker``
    from PATH (the container legs read the declared executable
    instead of a literal; a CI runner's docker sits elsewhere)."""
    import yaml
    try:
        doc = yaml.safe_load((FIXTURE_CONFIG / "cfg" / "executables.yml").read_text()) or {}
        for exe in doc.get("executables") or []:
            if isinstance(exe, dict) and exe.get("name") == "docker" and exe.get("binary"):
                binary = str(exe["binary"])
                if Path(binary).is_file() or shutil.which(binary):
                    return binary
    except (OSError, yaml.YAMLError):
        pass
    return "docker"


def plain(value: Any) -> Any:
    """The plaintext of a fixture value that may be an ``ENC[age:...]`` marker,
    opened with the fixture's TEST identity -- for tests that
    address roster entries by name in the raw YAML."""
    return kit.plain(value, FIXTURE_CONFIG / kit.IDENTITY_FILE)


def _credentials(monkeypatch) -> None:
    """Dummy okta / oktapam credentials, so command lists never depend on
    the developer's shell."""
    monkeypatch.setenv("OKTA_API_PRIVATE_KEY", "dummy")
    monkeypatch.setenv("TF_VAR_nos_coastal_modeling_cloud_sandbox_key", "dummy")
    monkeypatch.setenv("TF_VAR_nos_coastal_modeling_cloud_sandbox_secret", "dummy")


def _clouds(monkeypatch, retags: list[tuple[str, dict[str, str]]]) -> None:
    """The AWS stubs."""
    # The cloud discovery stubs: a LOAD never calls them --
    # the copy's meta-state/runtime-facts.yaml (record_network_facts) says
    # what they would answer -- but a real run's `discover` and a test's
    # `validate --online` do, and must get the same answers.
    from cs_image_system.aws_runtime import aws_utils
    monkeypatch.setattr(aws_utils, "get_vpc_map_and_default_vpc_id",
                        lambda session_config: ({v: {"subnets": []} for v in VPCS}, "default",
                                                _AnySecurityGroups()))
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    monkeypatch.setattr(AwsCloudBuilder, "query_provider_image",
                        lambda self, osb: (VENDOR_AMI, "amazon", {}))
    # The read-only state-query hooks would reach AWS/OPA: answer "nothing
    # of ours exists" by default. Tests of the query itself re-patch these
    # AFTER constructing their FixtureRun.
    monkeypatch.setattr(AwsCloudBuilder, "query_images", lambda self, series: [])
    # zero-drift-report: post-bake retagging would reach EC2; journal it.
    monkeypatch.setattr(AwsCloudBuilder, "retag_image",
                        lambda self, image_id, tags: retags.append((image_id, dict(tags))) or True)
    # the post-bake suite runs over the session command; the stub
    # answers PASS for every assertion the script carries (tests that need a
    # failing or dead session override this per test)
    monkeypatch.setattr(AwsCloudBuilder, "run_session_command",
                        passing_session(AwsCloudBuilder.run_session_command))


def _identity_provider(monkeypatch, retirements: list[tuple[str, str]]) -> None:
    """The Okta stubs."""
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    monkeypatch.setattr(OktaTfGroupBuilder, "query_state",
                        lambda self: {g.get_name(): {"present": True, "gid": 1}
                                      for g in self.get_groups_for_builder()})
    # the server registry ANSWERS here -- an empty, free one -- and
    # retirements are journaled. Silence would be refused by design (a run
    # that can launch will not trust an unreachable registry), and the
    # harness models a reachable OPA, not an absent one.
    monkeypatch.setattr(OktaTfGroupBuilder, "registered_servers", lambda self, group: [])
    monkeypatch.setattr(OktaTfGroupBuilder, "retire_servers_named",
                        lambda self, group, hostname: retirements.append((group, hostname)) or [])


def stub_environment(monkeypatch) -> list[str]:
    """Install every stub; returns the command journal.

    The test kit installs the core's stubs (it also holds the installed
    plugins to the contract once, as shipped, before any hook is replaced:
    tests/conftest.py does this at session start for the root suite; a
    package's tests and `tests/golden.py` run without that conftest). Each
    provider's stubs follow: the fixture's docker runtime names a daemon
    that exists nowhere (context csis-fixture-daemon), and its pull, its
    image listing, its retagging and its session are answered by the docker
    package's own stub as the clouds' are answered here, so no test reaches
    a daemon and the golden pins the docker emission."""
    retags: list[tuple[str, dict[str, str]]] = []
    retirements: list[tuple[str, str]] = []
    journal = kit.stub_core(monkeypatch, FIXTURE_CONFIG / kit.IDENTITY_FILE, stubs=(
        _credentials,
        lambda mp: _clouds(mp, retags),
        lambda mp: docker_testing.stub(mp, retags),
        roots_testing.stub,
        lambda mp: _identity_provider(mp, retirements),
    ))
    stub_environment.retags = retags  # type: ignore[attr-defined]
    stub_environment.retirements = retirements  # type: ignore[attr-defined]
    return journal


class FixtureRun:
    """One prepared config copy + context; ``run()`` drives lifecycles."""

    def __init__(self, tmp_path: Path, monkeypatch, dry_run: bool = True, config_root: Path | None = None,
                 overlays: list[Path] | None = None, undeclare: list[str] | None = None):
        self.journal = stub_environment(monkeypatch)
        self.retags: list[tuple[str, dict[str, str]]] = getattr(stub_environment, "retags", [])
        self.config_root = config_root or copy_config(tmp_path)
        self._cwd = os.getcwd()
        self.ctx = load_context(self.config_root, dry_run=dry_run, overlays=overlays, undeclare=undeclare)
        self.generated = self.config_root / "generated"
        self.meta_state = self.config_root / "meta-state"

    def run(self, lifecycles: list[str] | str = "all", *, apply: bool = True, commit: bool = False,
            state_query: bool = False, only: list[str] | None = None,
            force_bake: list[str] | None = None):
        summary = drive_lifecycles(self.ctx, lifecycles, apply=apply, commit=commit, state_query=state_query, only=only,
                         force_bake=force_bake)
        return summary

    def restore_cwd(self) -> None:
        os.chdir(self._cwd)


def private_plugin_cache(tmp_path: Path, roots: list[Path]) -> Path:
    """The suite's real-tofu test never shares the operator's provider
    cache -- `TF_PLUGIN_CACHE_DIR` is not safe under concurrent `init`, and a
    cycle that overlapped the bar failed on it. A private cache under the test's
    temporary directory, seeded by COPYING (never linking: tofu writes beside
    what it reads) the providers the roots require from the shared cache when
    one is there, so nothing is downloaded that need not be and nothing is
    written outside tmp_path."""
    private = tmp_path / "plugin-cache"
    private.mkdir(exist_ok=True)
    shared = os.environ.get("TF_PLUGIN_CACHE_DIR")
    if not shared or not Path(shared).is_dir():
        return private
    sources: set[str] = set()
    for r in roots:
        for tf in r.rglob("*.tf"):
            for src in re.findall(r'source\s*=\s*"([^"]+)"', tf.read_text()):
                if src.startswith((".", "/")) or ":" in src:      # a module path or URL
                    continue
                parts = src.split("/")
                if len(parts) == 2:
                    parts = ["registry.opentofu.org", *parts]
                if len(parts) == 3:
                    sources.add("/".join(parts))
    for src in sorted(sources):
        have = Path(shared) / src
        if have.is_dir() and not (private / src).exists():
            shutil.copytree(have, private / src)
    return private
