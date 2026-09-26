# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end characterization of the config-load pipeline over the frozen
fixture's cfg/ (``tests/fixtures/config``, stage 28).

Stage 32 retired the loader's base-only mode (it read no item kinds and no
command could request it); these tests load the whole tree.
"""
import os
import types
from pathlib import Path
from typing import Any, cast

import pytest

from v2_support import FIXTURE_CONFIG, copy_config

REPO = Path(__file__).resolve().parents[1]


def _reset_gtc_singleton():
    """GlobalTypeContext is @singleton-wrapped; clear the cached instance.

    The singleton factory ignores constructor args once an instance exists, so
    a test that needs a differently-configured context (e.g. base_only=False
    after a base_only=True test) must clear the closure's instances dict.
    """
    from cs_image_system.base import global_context as gc
    for cell in cast(Any, gc.GlobalTypeContext).__closure__:
        val = cell.cell_contents
        if isinstance(val, dict):
            val.clear()
            return
    raise AssertionError("singleton instances dict not found in closure")


@pytest.fixture
def cwd_guard():
    prev = os.getcwd()
    try:
        yield
    finally:
        os.chdir(prev)


class _AnySecurityGroups(dict):
    """Stubbed account SG map: membership always true. Which security groups
    exist is a live-account fact; the fixture's configured ids are data, not
    values these tests should restate."""
    def __contains__(self, key: object) -> bool:
        return True


@pytest.fixture(autouse=True)
def no_cloud(monkeypatch):
    """Config load finalizes AWS runtime models against live EC2 (VPC/subnet
    discovery). Stub it so these tests need no credentials -- they exercise
    the config pipeline, not AWS."""
    # The Okta workspace's finalization asserts its TF_VAR_* credentials exist
    # (okta_tf_workspace._require_tfvar); the V2 harness stubs them, and so
    # must these tests -- they had inherited them from the developer's shell,
    # which is why CI never passed (stage 18).
    monkeypatch.setenv("OKTA_API_PRIVATE_KEY", "dummy")
    monkeypatch.setenv("TF_VAR_nos_coastal_modeling_cloud_sandbox_key", "dummy")
    monkeypatch.setenv("TF_VAR_nos_coastal_modeling_cloud_sandbox_secret", "dummy")
    monkeypatch.setenv("CSIS_CONFIG_IDENTITY", str(FIXTURE_CONFIG / ".age-identity"))   # stage 33
    from cs_image_system.aws_runtime import aws_utils
    vpcs = ["vpc-0c78d0d63b7a100df", "vpc-0381e9f82c9ae68e7", "default"]
    monkeypatch.setattr(aws_utils, "get_vpc_map_and_default_vpc_id",
                        lambda session_config: ({v: {"subnets": []} for v in vpcs}, "default",
                                                _AnySecurityGroups()))
    # The gcloud runtime carries a real project now: stub its network
    # discovery too, config-derived (subnet ids are data, not test literals).
    import yaml as _yaml
    from cs_image_system.gcloud_runtime import gcp_utils

    def _gcp_network_map(session_config, clients=None):
        d = _yaml.safe_load((FIXTURE_CONFIG / "cfg" / "runtime-builders.yml").read_text()) or {}
        subnets = [{"subnet_id": s.get("subnet_id")}
                   for r in d.get("runtime_builders", []) if r.get("type") == "gcloud"
                   for s in (r.get("networking", {}) or {}).get("subnets") or []]
        return ({"default": {"subnets": subnets}}, "default", {})

    monkeypatch.setattr(gcp_utils, "get_network_map_and_default_network", _gcp_network_map)


def test_pipeline_loads_and_resolves_builders(monkeypatch, cwd_guard, tmp_path):
    monkeypatch.setenv("USER", "testuser")
    from cs_image_system.base.loader import load_plugins
    load_plugins()
    from cs_image_system.base.global_context import read_config_and_transform

    # over a COPY: loading creates the generation directories where it runs,
    # and the frozen fixture must never be written into (stage 28)
    cntx = types.SimpleNamespace(obj={})
    ctx = read_config_and_transform(cast(Any, cntx), copy_config(tmp_path), False)

    assert set(ctx.runtime_builders) == {"aws-east1", "aws-east2-runtime", "gcloud-east1", "west1"}
    assert "pckr-ebs-ans" in ctx.image_builders
    assert len(ctx.os_builders) >= 1


def test_string_stage_resolves_config_document(monkeypatch):
    """The string stage (cycle_main_yaml) resolves ENV/config over the real cfg."""
    monkeypatch.setenv("USER", "testuser")
    import glob
    import yaml
    from cs_image_system.base.template_utils import cycle_main_yaml

    def _extend(old, new):
        for k, v in new.items():
            if isinstance(v, list) and isinstance(old.get(k), list):
                old[k].extend(v)
            else:
                old[k] = v
        return old

    merged = {}
    for f in sorted(glob.glob(str(FIXTURE_CONFIG / "cfg" / "*.yml"))):
        with open(f) as fh:
            d = yaml.unsafe_load(fh)
            if isinstance(d, dict):
                _extend(merged, d)

    out = yaml.safe_load(cycle_main_yaml(yaml.dump(merged),
                                         addl={"execution": {"timestamp": "T"}}))
    assert out["config"]["systemuser"] == "testuser"
    # stage 22.6: these assertions used to ride on the fixture's
    # `output_image_name`, a key no model accepts and that stage 22.3
    # commented out. Template scoping is a property of the engine, not of any
    # one configuration key, so the test now owns its input and cannot be
    # broken again by a fixture edit.
    probe = yaml.safe_load(cycle_main_yaml(yaml.dump({
        "os_builders": [{
            "name": "probe-os", "family": "debian", "family_version": "11",
            "scoped": "{{ this.name }}-{{ this.family }}-{{ this.family_version }}",
            "runtimes": [{
                "name": "rt-a",
                "scoped": "AWS-{{ this.name }}-{{ this.parent.family }}"
                          "-{{ this.parent.family_version }}-{{ execution.timestamp }}",
            }],
        }]
    }), addl={"execution": {"timestamp": "T"}}))
    pob = probe["os_builders"][0]
    # nearest `this` = the os_builder
    assert pob["scoped"] == "probe-os-debian-11"
    # inside a runtime, nearest `this` = the runtime, `this.parent` = the os_builder
    assert pob["runtimes"][0]["scoped"] == "AWS-rt-a-debian-11-T"


def test_image_to_source_emits_psi_backed_data_block(monkeypatch, cwd_guard, tmp_path):
    """image_to_source consumes ProviderSpecificImages directly.

    Runs the pipeline over the fixture's cfg/ with the cloud image query
    stubbed, then converts an os-resolved BaseImage to packer HCL and asserts
    the data "amazon-ami" block carries the PSI's resolved image-id filter.
    """
    monkeypatch.setenv("USER", "testuser")
    from cs_image_system.base import registry
    from cs_image_system.base.orchestrator import Orchestrator, TemplateResolver

    registry.Registry().reset()
    TemplateResolver().flattened_map = {}
    Orchestrator().invalidate_converter()

    from cs_image_system.base.loader import load_plugins
    load_plugins()

    # Stub the cloud queries: no EC2/GCE calls during resolution.
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    monkeypatch.setattr(AwsCloudBuilder, "query_provider_image",
                        lambda self, osb: ("ami-0feedfacecafebeef", "amazon", {}))
    monkeypatch.setattr(GCPCloudBuilder, "query_provider_image",
                        lambda self, osb: ("debian-11-v1", "debian-cloud", {}))

    _reset_gtc_singleton()          # an earlier test's context (over the live tree) would leak in

    # This test's premise is a base image that still NEEDS a bake (an
    # os-resolved base attached to the image builder). Since convergent bakes
    # (stage 9) a current series head is skipped, and the live meta-state
    # records real AWS heads for every base (the last one, basic-rh-10@aws,
    # baked 2026-09-09) -- work on a copy with the lineage/pins stripped,
    # like the execution-run test below. (The frozen fixture carries no
    # meta-state at all since stage 28; the strip is kept as the guard.)
    import shutil
    import types
    root = tmp_path / "config"
    shutil.copytree(FIXTURE_CONFIG, root,
                    ignore=shutil.ignore_patterns("generated", ".terraform"))
    for f in ("lineage.yaml", "pins.yaml"):
        (root / "meta-state" / f).unlink(missing_ok=True)
    from cs_image_system.base.global_context import read_config_and_transform
    ctx = read_config_and_transform(cast(Any, types.SimpleNamespace(obj={})),
                                    root, False)

    from cs_image_system.base.commands.resolve import predefined_resolve
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    assert predefined_resolve(ctx, ExecutionLifecyclePhase.RESOLUTION, True)

    # Resolution registered a resolved PSI per os-builder x runtime.
    psis = ctx.provider_specific_images
    assert psis, "resolution should have registered provider-specific images"
    assert any(p.identifier == "ami-0feedfacecafebeef" and p.is_resolved()
               for p in psis.values())

    ib = ctx.image_builders["pckr-ebs-ans"]
    runtime = ib.model.get_runtime_provider()
    base_images = [i for i in ib.get_images(os_builder=True)
                   if i.get_image_runtime_subconfig_for_runtime(runtime)]
    assert base_images, "os-resolved base images should be attached to the image builder"
    bi = base_images[0]

    lines = cast(Any, ib).image_to_source("amazon-ebs", runtime, bi)
    hcl = "\n".join(lines)
    assert f'data "amazon-ami" "{bi.name}_{runtime}"' in hcl
    assert '"image-id" = "ami-0feedfacecafebeef"' in hcl.replace("  ", " ") or \
           "ami-0feedfacecafebeef" in hcl
    assert f'source "amazon-ebs" "{bi.name}"' in hcl
    assert f"data.amazon-ami.{bi.name}_{runtime}.id" in hcl


def test_execution_run_defers_base_images_no_query_no_build(monkeypatch, cwd_guard, tmp_path):
    """Execution runs never build base images.

    Two-run spec: the base run (--base-only) builds base images; the execution
    run consumes its RESULTS. So resolution here must make no vendor-image
    cloud query, must not hand base images to the image builder (packer never
    builds them), and must register a DEFERRED PSI per base image whose name
    pattern locates the base run's built artifact -- which chained images then
    consume as an owners=self / most_recent data lookup.
    """
    monkeypatch.setenv("USER", "testuser")
    from cs_image_system.base import registry
    from cs_image_system.base.orchestrator import Orchestrator, TemplateResolver

    registry.Registry().reset()
    TemplateResolver().flattened_map = {}
    Orchestrator().invalidate_converter()
    _reset_gtc_singleton()

    from cs_image_system.base.loader import load_plugins
    load_plugins()

    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder

    def _no_query(self, osb):
        raise AssertionError(
            "execution runs must not query the provider for base images")
    monkeypatch.setattr(AwsCloudBuilder, "query_provider_image", _no_query)
    monkeypatch.setattr(GCPCloudBuilder, "query_provider_image", _no_query)

    # This test's premise is a FRESH system (no pins): since the first live
    # bake (2026-08-31), the live tree's committed meta-state recorded real
    # builds, and a chained image would correctly pin to the series head
    # (N17) instead of emitting the deferred name-pattern lookup. Work on a
    # copy with the lineage/pins stripped (the frozen fixture carries none
    # since stage 28; the strip is kept as the guard).
    import shutil
    root = tmp_path / "config"
    shutil.copytree(FIXTURE_CONFIG, root,
                    ignore=shutil.ignore_patterns("generated", ".terraform"))
    for f in ("lineage.yaml", "pins.yaml"):
        (root / "meta-state" / f).unlink(missing_ok=True)

    from cs_image_system.base.global_context import read_config_and_transform
    ctx = read_config_and_transform(cast(Any, types.SimpleNamespace(obj={})),
                                    root, False)

    from cs_image_system.base.commands.resolve import predefined_resolve
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    assert predefined_resolve(ctx, ExecutionLifecyclePhase.RESOLUTION, False)

    from cs_image_system.base.models.provider_specific_image import PSISourceKind
    base_psis = [p for p in ctx.provider_specific_images.values()
                 if p.source_kind == PSISourceKind.OS_BUILDER]
    assert base_psis, "each os builder x runtime should register a base-image PSI"
    assert all(not p.is_resolved() and p.deferred_name_pattern for p in base_psis)
    # User-image deferred PSIs are still created alongside.
    assert any(p.source_kind == PSISourceKind.IMAGE and not p.is_resolved()
               for p in ctx.provider_specific_images.values())

    for name, ib in ctx.image_builders.items():
        assert ib.get_images(os_builder=True) == [], (
            f"execution run handed base images to image builder {name}")

    # A chained image (source_image = a base image) emits the deferred lookup
    # against the base run's artifact, not a vendor image-id.
    ib = ctx.image_builders["pckr-ebs-ans"]
    runtime = ib.model.get_runtime_provider()
    chained = [i for i in ib.get_images(os_builder=False)
               if i.source_image and i.source_image in ctx.os_builders
               and i.get_image_runtime_subconfig_for_runtime(runtime)]
    assert chained, "fixture should include an image chained from a base image"
    img = chained[0]
    hcl = "\n".join(cast(Any, ib).image_to_source("amazon-ebs", runtime, img))
    base_psi = ctx.get_provider_specific_image(cast(str, img.source_image), runtime)
    assert base_psi is not None and base_psi.deferred_name_pattern is not None
    assert base_psi.deferred_name_pattern in hcl
    assert '"self"' in hcl and "most_recent" in hcl
    assert "image-id" not in hcl
