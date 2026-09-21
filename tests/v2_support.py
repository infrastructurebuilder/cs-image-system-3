# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Shared harness for the V2 gate tests.

Every V2 test runs the real pipeline over a private COPY of the frozen
fixture (``tests/fixtures/config``, stage 28: owned by the tests, never a
live configuration) with all external touchpoints stubbed:

* no cloud: AWS networking discovery, vendor-AMI queries and GCP queries are
  replaced; nothing in these tests can read or write AWS/Okta;
* no tools: ``ExecutableModel.execute`` is journaled, never run;
* deterministic: the run timestamp and ``USER`` are pinned, and dummy okta /
  oktapam credentials are present so command lists never depend on the
  developer's shell.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import types
from datetime import datetime
from pathlib import Path
from typing import Any, cast

REPO = Path(__file__).resolve().parents[1]
FIXTURE_CONFIG = REPO / "tests" / "fixtures" / "config"     # frozen (stage 28); the live tree is elsewhere
V1_BASELINE = REPO / "tests" / "fixtures" / "v1_baseline"

FIXED_NOW = datetime(2026, 8, 26, 12, 0, 0)
FIXED_TIMESTAMP = "20260826_120000"          # per the fixture's dateformat
FIXED_RUN_ID = "2026_08_26t12_00_00"         # iso_sanitized

VPCS = ["vpc-0c78d0d63b7a100df", "vpc-0381e9f82c9ae68e7", "default"]
VENDOR_AMI = "ami-0feedfacecafebeef"


class _AnySecurityGroups(dict):
    """Stubbed account SG map: membership always true. Which security groups
    exist is a live-account fact; the fixture's configured ids are data, not
    values these tests should restate."""
    def __contains__(self, key: object) -> bool:
        return True


class _FixedDT(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return FIXED_NOW


def copy_config(tmp_path: Path, name: str = "config") -> Path:
    """A private copy of the frozen fixture (without any generated output).
    The transient apply_* flags are normalized to false -- a live run's
    TEMP flag flip must never leak into tests (found live during the first
    GCP apply, when the fixture was still the live tree); tests that want
    a flag on set ``ctx.config`` (and the file, for apply-check)
    themselves."""
    import re
    dst = tmp_path / name
    # The frozen fixture carries no generated output and no meta-state
    # (records of live cloud resources); the ignore list is the guard that
    # keeps it so should either ever be copied in.
    shutil.copytree(FIXTURE_CONFIG, dst,
                    ignore=shutil.ignore_patterns("generated", "meta-state", ".git", ".DS_Store"))
    cfg = dst / "cfg" / "_config.yml"
    cfg.write_text(re.sub(r"^(  apply_\w+:) \S+.*$", r"\1 false", cfg.read_text(), flags=re.M))
    # The live GCE runtime declares `ephemeral: true` (stage 10.4, rule 58);
    # copies start non-ephemeral and tests that want it declare it.
    rb = dst / "cfg" / "runtime-builders.yml"
    rb.write_text(re.sub(r"^(\s+ephemeral:) true.*$", r"\1 false", rb.read_text(), flags=re.M))
    # The suite's instance subjects (test, test2, gce-test) are declared in
    # the fixture itself since stage 39; nothing is injected here.
    return dst


def plain(value: Any) -> Any:
    """The plaintext of a fixture value that may be an ``ENC[age:...]`` marker
    (stage 33), opened with the fixture's TEST identity -- for tests that
    address roster entries by name in the raw YAML."""
    from cs_image_system.base.encryption import _identities_for, decrypt_marker, is_marker
    if is_marker(value):
        return decrypt_marker(value, _identities_for(str(FIXTURE_CONFIG / ".age-identity")))
    return value


def reset_singletons() -> None:
    from cs_image_system.base import global_context as gc
    from cs_image_system.base import registry
    from cs_image_system.base.orchestrator import Orchestrator, TemplateResolver
    from cs_image_system.hashicorp_utils.collector import PackerCollector, TerraformCollector
    registry.Registry().reset()
    TemplateResolver().flattened_map = {}
    from cs_image_system.base.orchestrator import reset_unresolved_fks
    reset_unresolved_fks()
    Orchestrator().invalidate_converter()
    TerraformCollector().reset()
    PackerCollector().reset()
    for cell in cast(Any, gc.GlobalTypeContext).__closure__:
        val = cell.cell_contents
        if isinstance(val, dict):
            val.clear()
    from cs_image_system.base.loader import load_plugins
    load_plugins()


def stub_environment(monkeypatch) -> list[str]:
    """Install every stub; returns the command journal."""
    monkeypatch.setenv("USER", "testuser")
    monkeypatch.setenv("OKTA_API_PRIVATE_KEY", "dummy")
    monkeypatch.setenv("TF_VAR_nos_coastal_modeling_cloud_sandbox_key", "dummy")
    monkeypatch.setenv("TF_VAR_nos_coastal_modeling_cloud_sandbox_secret", "dummy")
    # stage 33: the frozen fixture's TEST identity opens its encrypted values
    monkeypatch.setenv("CSIS_CONFIG_IDENTITY", str(FIXTURE_CONFIG / ".age-identity"))

    from cs_image_system.base import global_context as gc
    monkeypatch.setattr(gc, "datetime", _FixedDT)

    from cs_image_system.aws_runtime import aws_utils
    monkeypatch.setattr(aws_utils, "get_vpc_map_and_default_vpc_id",
                        lambda session_config: ({v: {"subnets": []} for v in VPCS}, "default",
                                                _AnySecurityGroups()))
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.gcloud_runtime import gcp_utils
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    def _gcp_network_map(session_config, clients=None):
        # Config-derived like the SG stub: which subnets exist is a
        # live-account fact, and the fixture's ids are data these tests must
        # not restate. The my-project entries serve the gce_overlay tests.
        import yaml as _yaml
        subnets = [{"subnet_id": "projects/my-project/regions/us-east1/subnetworks/default"},
                   {"subnet_id": "projects/my-project/regions/us-east1/subnetworks/custom-subnet-1"}]
        d = _yaml.safe_load((FIXTURE_CONFIG / "cfg" / "runtime-builders.yml").read_text()) or {}
        for r in d.get("runtime_builders", []):
            if r.get("type") == "gcloud":
                for s in (r.get("networking", {}) or {}).get("subnets") or []:
                    subnets.append({"subnet_id": s.get("subnet_id")})
        return ({"default": {"subnets": subnets}}, "default", {})

    monkeypatch.setattr(gcp_utils, "get_network_map_and_default_network", _gcp_network_map)
    monkeypatch.setattr(AwsCloudBuilder, "query_provider_image",
                        lambda self, osb: (VENDOR_AMI, "amazon", {}))
    monkeypatch.setattr(GCPCloudBuilder, "query_provider_image",
                        lambda self, osb: ("debian-11-v1", "debian-cloud", {}))
    # The read-only state-query hooks would reach AWS/OPA: answer "nothing
    # of ours exists" by default. Tests of the query itself re-patch these
    # AFTER constructing their V2Run.
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    from cs_image_system.tf_ebs_instance_plugin.tf_storage_builder import TofuStorageBuilder
    monkeypatch.setattr(AwsCloudBuilder, "query_images", lambda self, series: [])
    monkeypatch.setattr(GCPCloudBuilder, "query_images", lambda self, series: [])
    # zero-drift-report: post-bake retagging would reach EC2; journal it.
    retags: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(AwsCloudBuilder, "retag_image",
                        lambda self, image_id, tags: retags.append((image_id, dict(tags))) or True)
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    # stage 14: the post-bake suite runs over the session command; the stub
    # answers PASS for every assertion the script carries (tests that need a
    # failing or dead session override this per test)
    import re as _re
    _real_aws_session = AwsCloudBuilder.run_session_command
    _real_gcp_session = GCPCloudBuilder.run_session_command

    def _session_stub(real):
        def _run(self, name, script, timeout=300):
            idx = _re.findall(r'CSIS_TEST (\d+) PASS', script)
            if not idx:                      # an unmount or any other session: the real hook (its
                return real(self, name, script, timeout)   # subprocess is what those tests fake)
            return 0, "".join(f"CSIS_TEST {i} PASS\n" for i in sorted(set(idx), key=int))
        return _run
    monkeypatch.setattr(AwsCloudBuilder, "run_session_command", _session_stub(_real_aws_session))
    monkeypatch.setattr(GCPCloudBuilder, "run_session_command", _session_stub(_real_gcp_session))
    monkeypatch.setattr(GCPCloudBuilder, "retag_image",                    # ledger 66: GCE relabels too
                        lambda self, image_id, tags: retags.append((image_id, dict(tags))) or True)
    stub_environment.retags = retags  # type: ignore[attr-defined]
    monkeypatch.setattr(TofuStorageBuilder, "query_state",
                        lambda self: {s.get_name(): {"present": False, "type": self.capability_type()}
                                      for s in self.model._storages})
    monkeypatch.setattr(OktaTfGroupBuilder, "query_state",
                        lambda self: {g.get_name(): {"present": True, "gid": 1}
                                      for g in self.get_groups_for_builder()})
    # stage 55: the server registry ANSWERS here -- an empty, free one -- and
    # retirements are journaled. Silence would be refused by design (a run
    # that can launch will not trust an unreachable registry), and the
    # harness models a reachable OPA, not an absent one.
    retirements: list[tuple[str, str]] = []
    monkeypatch.setattr(OktaTfGroupBuilder, "registered_servers", lambda self, group: [])
    monkeypatch.setattr(OktaTfGroupBuilder, "retire_servers_named",
                        lambda self, group, hostname: retirements.append((group, hostname)) or [])
    stub_environment.retirements = retirements  # type: ignore[attr-defined]

    journal: list[str] = []
    from cs_image_system.base.models.executable import ExecutableModel

    def _fake_execute(self, *args, skips=False):
        cmd = [self.binary or self.name] + list(self.args or []) + list(args)
        journal.append(f"{self.working_directory}: {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ExecutableModel, "execute", _fake_execute)

    from cs_image_system.base.commands import validate as _validate
    monkeypatch.setattr(_validate, "check_executables_exist_and_versions", lambda ctx: [])
    return journal


def load_context(config_root: Path, dry_run: bool = True, overlays: list[Path] | None = None,
                 undeclare: list[str] | None = None):
    """Fresh singletons + a GlobalTypeContext over ``config_root`` (plus any
    transient ``--overlay`` files, stage 8, and ``--undeclare`` specs, stage 28)."""
    reset_singletons()
    from cs_image_system.base.global_context import read_config_and_transform
    return read_config_and_transform(cast(Any, types.SimpleNamespace(obj={})),
                                     config_root, False, [], False, dry_run=dry_run,
                                     overlays=list(overlays or []), undeclare=list(undeclare or []))


def run_v2(lifecycles: list[str] | str = "all", *, apply: bool = True, commit: bool = False,
           state_query: bool = False, only: list[str] | None = None,
           force_bake: list[str] | None = None):
    """``state_query`` is OFF here: the real hooks would reach AWS/OPA. Tests
    of the pre-run query stub the hooks and pass ``state_query=True``."""
    from cs_image_system.base.commands.run_lifecycles import run_lifecycles
    from cs_image_system.base.lifecycles import parse_lifecycles
    names = [lifecycles] if isinstance(lifecycles, str) else lifecycles
    return run_lifecycles(parse_lifecycles(names), apply=apply, commit=commit,
                          state_query=state_query, only=only, force_bake=force_bake)


class V2Run:
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
        summary = run_v2(lifecycles, apply=apply, commit=commit, state_query=state_query, only=only,
                         force_bake=force_bake)
        return summary

    def restore_cwd(self) -> None:
        os.chdir(self._cwd)


def tree(root: Path, *, ignore_parts: tuple[str, ...] = (".terraform", "temp_assets")) -> dict[str, str]:
    """``{relative path: text}`` for every file under root."""
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in ignore_parts for part in rel.parts):
            continue
        out[str(rel)] = p.read_text()
    return out


def command_lines(script_text: str) -> list[str]:
    """The executable lines of a runner script (no shebang/comments/set/cd)."""
    lines = []
    for line in script_text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("set ") or s == 'cd "$(dirname "$0")"' or s.startswith("CSIS_ROOT="):
            continue
        lines.append(s)
    return lines
