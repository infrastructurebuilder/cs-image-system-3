# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 62 step 5: the example configurations under docs/examples/ load and
validate.

Three trees, each in the shape of a real configuration root:

* ``standard-aws`` -- the smallest tree for the AWS plugin set: one group,
  one storage, one base image, one instance image, one instance;
* ``standard-gce`` -- the same for the GCE plugin set;
* ``complete`` -- every plugin the workspace ships, every documented field,
  every variation, plus the alias pool and a storage-state record so the
  archived and destroyed requests are legal.

Each is copied to a private directory, loaded over the V2 harness (every
cloud and tool stubbed, the frozen fixture's TEST identity exported) and
run through the ``validate`` command's checks; the standard trees are
pinned minimal, the complete tree is pinned to name every plugin type, and
every ``ENC[age:...]`` marker in the three trees must open with the test
identity. Documentation only: nothing here changes what the code does.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml

from v2_support import load_context, stub_environment

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "docs" / "examples"
STANDARD = ["standard-aws", "standard-gce"]
TREES = [*STANDARD, "complete"]

# The `type:` keys each plugin package answers to (docs/PLUGINS.md and the
# packages' models). Packages that register no `type:` (base, system, the
# hashicorp-utils library) and the dummy plugin (an extension template and
# test double, never a configured builder) are not part of the contract.
PLUGIN_TYPES: dict[str, set[str]] = {
    "ansible-plugin": {"ansible"},
    "aws-runtime-plugin": {"aws"},
    "bash-mod-plugin": {"bash-remote"},
    "default-os-plugin": {"rhel", "debian", "ubuntu"},      # fedora and alpine are the same plugin, unused here
    "gcloud-runtime-plugin": {"gcloud"},
    "gcs-state-plugin": {"gcs"},
    "local-state-plugin": {"local"},
    "okta-opa-plugin": {"okta-tf", "okta-tf-ro"},
    "packer-plugin": {"packer-ebs", "packer-gce"},
    "tf-ebs-instance-plugin": {"tofu", "tf-aws-ebs", "tf-aws-efs", "tf-aws-s3"},
    "tf-gcp-plugin": {"tofu-gce", "tf-gcp-pd", "tf-gcp-filestore", "tf-gcp-gcs"},
    "tf-s3-state-plugin": {"s3"},
}
NOT_PLUGINS = {"base", "system", "hashicorp-utils", "dummy-plugin"}
MARKER = re.compile(r"ENC\[age:[A-Za-z0-9+/=]+\]")


def copy_example(tmp_path: Path, name: str) -> Path:
    """A private copy of an example root (no generated output, no VCS
    litter); the complete tree's hand-written meta-state files travel with it."""
    dst = tmp_path / name
    shutil.copytree(EXAMPLES / name, dst, ignore=shutil.ignore_patterns("generated", ".git", ".DS_Store"))
    return dst


def _runtimes(root: Path) -> list[dict]:
    out: list[dict] = []
    for p in sorted((root / "cfg").glob("*.y*ml")):
        doc = yaml.safe_load(p.read_text()) or {}
        out.extend(doc.get("runtime_builders") or [])
    return out


def stub_networks_from(monkeypatch, root: Path) -> None:
    """The harness answers cloud discovery from the frozen fixture's ids; an
    example tree names its own placeholders, so the answers come from the
    tree under test instead (which VPCs and subnets exist is a live-account
    fact these tests must not restate)."""
    from cs_image_system.aws_runtime import aws_utils
    from cs_image_system.gcloud_runtime import gcp_utils
    runtimes = _runtimes(root)

    class _AnySecurityGroups(dict):
        def __contains__(self, key: object) -> bool:
            return True

    vpcs = {"default"} | {str((r.get("networking") or {}).get("network") or "default")
                          for r in runtimes if r.get("type") == "aws"}
    monkeypatch.setattr(aws_utils, "get_vpc_map_and_default_vpc_id",
                        lambda session_config: ({v: {"subnets": []} for v in vpcs}, "default",
                                                _AnySecurityGroups()))
    networks: dict[str, dict] = {"default": {"subnets": []}}
    for r in runtimes:
        if r.get("type") != "gcloud":
            continue
        net = (r.get("networking") or {})
        name = str(net.get("network") or "default")
        entry = networks.setdefault(name, {"subnets": []})
        for s in net.get("subnets") or []:
            entry["subnets"].append({"subnet_id": s.get("subnet_id")})
    monkeypatch.setattr(gcp_utils, "get_network_map_and_default_network",
                        lambda session_config, clients=None: (networks, "default", {}))


def stub_opa_credentials_from(monkeypatch, root: Path) -> None:
    """An okta-tf builder whose `key`/`secret` are left at default asserts, AT
    LOAD, that TF_VAR_<team>_key and _secret exist (the manual says "at
    finalize"); the harness sets them for the fixture's team, so the example
    trees' placeholder teams get dummies here."""
    from cs_image_system.base import utils
    for p in sorted((root / "cfg").glob("*.y*ml")):
        doc = yaml.safe_load(p.read_text()) or {}
        for key in ("group_builders", "user_builders"):
            for b in doc.get(key) or []:
                if isinstance(b, dict) and b.get("team"):
                    team = utils.super_safe_name(str(b["team"]))
                    monkeypatch.setenv(f"TF_VAR_{team}_key", "dummy")
                    monkeypatch.setenv(f"TF_VAR_{team}_secret", "dummy")


@pytest.fixture(params=TREES)
def tree(request, tmp_path, monkeypatch):
    stub_environment(monkeypatch)
    root = copy_example(tmp_path, request.param)
    stub_networks_from(monkeypatch, root)
    stub_opa_credentials_from(monkeypatch, root)
    ctx = load_context(root, dry_run=True)
    return request.param, root, ctx


def _validation_errors(ctx) -> list[str]:
    from cs_image_system.base.commands.run_lifecycles import validate_only
    return validate_only(ctx)


def test_every_example_loads_and_validates(tree):
    name, root, ctx = tree
    assert _validation_errors(ctx) == [], name


def test_every_example_has_the_shape_of_a_configuration_root():
    for name in TREES:
        root = EXAMPLES / name
        for rel in ("README.md", "cfg/_config.yml", "groups", "storages", "images", "instances",
                    "base_images", "overlays", ".age-identity", ".age-recipient"):
            assert (root / rel).exists(), f"{name} lacks {rel}"
        fixture = REPO / "tests" / "fixtures" / "config"
        for f in (".age-identity", ".age-recipient"):
            assert (root / f).read_text() == (fixture / f).read_text(), f"{name}/{f} is not the TEST identity"


def test_the_standard_trees_are_minimal(tree):
    name, root, ctx = tree
    if name not in STANDARD:
        pytest.skip("the complete tree is anything but minimal")
    assert len(ctx.groups) == 1, [g.get_name() for g in ctx.groups]
    assert len(ctx.storages) == 1, [s.get_name() for s in ctx.storages]
    assert len(ctx.os_builders) == 1, sorted(ctx.os_builders)
    assert len(ctx.images) == 1, [i.get_name() for i in ctx.images]
    assert len(ctx.instances) == 1, [i.get_name() for i in ctx.instances]


def test_the_standard_trees_use_their_cloud_alone():
    for name, runtime in (("standard-aws", "aws"), ("standard-gce", "gcloud")):
        types = {r.get("type") for r in _runtimes(EXAMPLES / name)}
        assert types == {runtime}, f"{name} declares runtimes of types {types}"


def _builder_types(root: Path) -> set[str]:
    """Every `type:` a builder entry under cfg/ declares (not the collection
    items, whose `type` names a builder rather than a plugin)."""
    out: set[str] = set()
    for p in sorted((root / "cfg").glob("*.y*ml")):
        doc = yaml.safe_load(p.read_text()) or {}
        for key, entries in doc.items():
            if key == "executables" or not isinstance(entries, list):
                continue
            for e in entries:
                if isinstance(e, dict) and e.get("type"):
                    out.add(str(e["type"]))
    return out


def test_the_complete_tree_declares_every_plugin_the_workspace_ships():
    packages = {p.name for p in (REPO / "packages").iterdir()
                if p.is_dir() and (p / "pyproject.toml").exists()}
    plugins = packages - NOT_PLUGINS
    assert plugins == set(PLUGIN_TYPES), "a plugin package appeared or left: update PLUGIN_TYPES"
    for pkg in plugins:
        assert "entry-points" in (REPO / "packages" / pkg / "pyproject.toml").read_text(), f"{pkg} registers no entry point"
    used = _builder_types(EXAMPLES / "complete")
    for pkg, types in sorted(PLUGIN_TYPES.items()):
        missing = types - used
        assert not missing, f"complete: {pkg} type(s) {sorted(missing)} are not declared"


def test_every_marker_in_the_examples_opens_with_the_test_identity(monkeypatch):
    stub_environment(monkeypatch)
    from cs_image_system.base.encryption import _identities_for, decrypt_marker
    identities = _identities_for(str(REPO / "tests" / "fixtures" / "config" / ".age-identity"))
    seen = 0
    for name in TREES:
        for p in sorted((EXAMPLES / name).rglob("*")):
            if not p.is_file() or p.suffix not in (".yml", ".yaml", ".md", ".txt"):
                continue
            for m in MARKER.finditer(p.read_text()):
                assert decrypt_marker(m.group(0), identities), f"{p}: a marker that opens to nothing"
                seen += 1
    assert seen > 0, "the examples carry no encrypted value"


def test_the_prose_carries_no_em_dash():
    for name in TREES:
        for p in sorted((EXAMPLES / name).rglob("*")):
            if p.is_file() and p.suffix in (".md", ".yml", ".yaml", ".sh", ".txt"):
                assert "—" not in p.read_text(), f"{p} carries an em-dash"


OVERLAY_KEYS = {"config", "users", "groups", "storages", "images", "instances", "base_images"}


def test_every_overlay_has_the_documented_shape():
    for name in TREES:
        for p in sorted((EXAMPLES / name / "overlays").glob("*.y*ml")):
            doc = yaml.safe_load(p.read_text())
            assert isinstance(doc, dict) and doc, p
            assert set(doc) <= OVERLAY_KEYS, f"{p}: keys {sorted(set(doc) - OVERLAY_KEYS)} are not overlay keys"
            for key, value in doc.items():
                if key == "config":
                    assert isinstance(value, dict), p
                else:
                    assert isinstance(value, list) and all(isinstance(e, dict) and e.get("name") for e in value), p


@pytest.mark.parametrize("overlay", ["apply-identity-and-storage", "gce-cycle-launch", "gce-cycle-decommission",
                                     "archive-volume", "gce-cycle-storage-teardown"])
def test_the_complete_tree_loads_under_each_overlay(tmp_path, monkeypatch, overlay):
    stub_environment(monkeypatch)
    root = copy_example(tmp_path, "complete")
    stub_networks_from(monkeypatch, root)
    stub_opa_credentials_from(monkeypatch, root)
    ctx = load_context(root, dry_run=True, overlays=[root / "overlays" / f"{overlay}.yaml"])
    errors = _validation_errors(ctx)
    if overlay == "gce-cycle-storage-teardown":
        # the documented refusal: a never-applied, still-attached storage may
        # not be requested destroyed (the overlay is the pattern, not a plan)
        assert errors and all("gce_data" in e or "gce_bucket" in e for e in errors), errors
    else:
        assert errors == [], errors
    if overlay == "gce-cycle-launch":
        assert any(i.get_name() == "gce-cycle" for i in ctx.instances)
    if overlay == "gce-cycle-decommission":
        assert not any(i.get_name() == "gce-node" for i in ctx.instances)


def test_the_complete_tree_carries_every_variation(tree):
    name, root, ctx = tree
    if name != "complete":
        pytest.skip("the standard trees are minimal by design")
    from cs_image_system.base.lineage import image_policy_of, parent_policy_of
    assert {parent_policy_of(i) for i in ctx.images} == {"pinned", "follow"}
    assert {image_policy_of(i) for i in ctx.instances} == {"pinned", "follow"}
    assert {bool(i.ephemeral) for i in ctx.instances} == {True, False}
    assert {s.state for s in ctx.storages} == {"active", "archived", "destroyed"}
    assert {rt.model.type_ for rt in ctx.runtime_builders.values()} == {"aws", "gcloud"}
    assert {osb.model.family for osb in ctx.os_builders.values()} == {"rhel", "debian", "ubuntu"}
    assert {b.model.type_ for b in ctx.state_backends.values()} == {"s3", "local", "gcs"}
    assert any(getattr(g.model, "workload_connection", None) for g in ctx.group_builders.values())
    assert (root / "meta-state" / "aliases.txt").is_file()
    assert any(i.get_name() == "gce-node" for i in ctx.instances)
