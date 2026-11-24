# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The starters that declare a provider released elsewhere, with every provider installed.

``standard-gce`` and ``complete`` declare the Google Cloud family, and
``standard-aws`` and ``complete`` declare Okta groups: the family and the
Okta identity plugin are released from their own repositories, so this
workspace's venv holds neither, and ``tests/test_docs_examples.py`` cannot
load these trees. These tests can: ``just test-cloud-starters`` runs them
with the family and the plugin layered in from the index by the
``gcloud`` and ``okta`` extras' ranges (spec 005, research R11; spec 008,
T047), a ``full-test`` leg and a step of CI's ``live`` job. Each starter
validates; ``standard-gce`` and ``standard-aws`` dry-run every lifecycle;
``complete`` loads under each of its overlays and carries every variation.
The Okta plugin asks only that its credentials be present at a load (spec
008, T003), so the starters get dummy ones (``stub_opa_credentials_from``)
and nothing reaches Okta. The default collection leaves
this directory out (``norecursedirs`` in ``pyproject.toml``), and the recipe
runs it under the strict session, so a missing family fails instead of
skipping.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from harness import FIXED_CHECKED_AT, drive_lifecycles, load_context, record_network_facts, stub_environment
from test_docs_examples import (
    _runtimes,
    _validation_errors,
    copy_example,
    stub_networks_from,
    stub_opa_credentials_from,
)


def _gcloud(monkeypatch, root: Path) -> None:
    """The Google Cloud family's own stubs over ``root``'s declarations, and
    its network facts merged into the record the harness wrote for AWS."""
    # the family is layered in by `just test-cloud-starters`; this venv does not hold it
    from cs_image_system.gcloud_runtime import testing as gcloud_testing  # pyright: ignore[reportMissingImports]
    gcloud_testing.stub(monkeypatch)
    gcloud_testing.stub_declared_networks(monkeypatch, _runtimes(root))
    path = record_network_facts(root)
    aws = yaml.safe_load(path.read_text())["runtimes"]
    gcloud_testing.record_runtime_facts(root, FIXED_CHECKED_AT)
    gce = yaml.safe_load(path.read_text())["runtimes"]
    path.write_text(yaml.safe_dump({"runtimes": {**aws, **gce}}, sort_keys=True, default_flow_style=False))


def _starter(tmp_path: Path, monkeypatch, rendered_starters: Path, name: str, overlays: tuple[str, ...] = ()):
    stub_environment(monkeypatch)
    # `complete` pins one AWS base by its image id, which a dry run's resolution looks up by id;
    # the harness answers the vendor query, so the lookup by id is answered here, as the pinned id itself
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    monkeypatch.setattr(AwsCloudBuilder, "query_provider_image_by_id",
                        lambda self, os_builder, image_id: (str(image_id), "self", {}))
    root = copy_example(tmp_path, name, rendered_starters)
    stub_networks_from(monkeypatch, root)
    _gcloud(monkeypatch, root)
    stub_opa_credentials_from(monkeypatch, root)
    ctx = load_context(root, dry_run=True, overlays=[root / "overlays" / f"{o}.yaml" for o in overlays])
    return root, ctx


def _complete(tmp_path: Path, monkeypatch, rendered_starters: Path, overlays: tuple[str, ...] = ()):
    return _starter(tmp_path, monkeypatch, rendered_starters, "complete", overlays)


@pytest.mark.parametrize("name", ["standard-gce"])
def test_a_google_cloud_starter_validates_and_dry_runs_every_lifecycle(tmp_path, monkeypatch, name, rendered_starters):
    """FR-012: with the family installed, the Google Cloud starter validates and dry-runs every lifecycle.
    `complete` validates (the tests below) but does not dry-run: its AWS chain `imgfile-basic-cloudflow`
    on `aws-east1` names a parent with no build there, which a fresh tree's dry run refuses -- an AWS
    matter, not the Google Cloud family's, recorded in spec 005's T078."""
    cwd = os.getcwd()
    try:
        root, ctx = _starter(tmp_path, monkeypatch, rendered_starters, name)
        assert _validation_errors(ctx) == []
        assert "gcloud" in {rt.model.type_ for rt in ctx.runtime_builders.values()}
        summary = drive_lifecycles(ctx, "all", apply=False)
        assert summary.ok, summary.error
        emitted = {p.relative_to(root / "generated").parts[0] for p in (root / "generated").rglob("*") if p.is_file()}
        assert {"base-image", "instance-image"} <= emitted, sorted(emitted)
        assert any("gce" in str(p) for p in (root / "generated").rglob("*.tf")), "no Google Cloud root was emitted"
    finally:
        os.chdir(cwd)


def test_the_okta_starter_validates_and_dry_runs_every_lifecycle(tmp_path, monkeypatch, rendered_starters):
    """Spec 008, T047: with the Okta plugin from the index, ``standard-aws``
    (its groups on Okta's builders) validates and dry-runs every lifecycle,
    emitting its Okta identity root."""
    cwd = os.getcwd()
    try:
        root, ctx = _starter(tmp_path, monkeypatch, rendered_starters, "standard-aws")
        assert _validation_errors(ctx) == []
        assert {"okta"} <= {gb.identity_type() for gb in ctx.group_builders.values()}
        summary = drive_lifecycles(ctx, "all", apply=False)
        assert summary.ok, summary.error
        emitted = {p.relative_to(root / "generated").parts[0] for p in (root / "generated").rglob("*") if p.is_file()}
        assert {"base-image", "identity", "instance-image"} <= emitted, sorted(emitted)
    finally:
        os.chdir(cwd)


@pytest.mark.parametrize("overlay", ["apply-identity-and-storage", "gce-cycle-launch", "gce-cycle-decommission",
                                     "archive-volume", "gce-cycle-storage-teardown"])
def test_the_complete_tree_loads_under_each_overlay(tmp_path, monkeypatch, overlay, rendered_starters):
    _root, ctx = _complete(tmp_path, monkeypatch, rendered_starters, (overlay,))
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


def test_the_complete_tree_carries_every_variation(tmp_path, monkeypatch, rendered_starters):
    root, ctx = _complete(tmp_path, monkeypatch, rendered_starters)
    assert _validation_errors(ctx) == []
    from cs_image_system.base.lineage import image_policy_of, parent_policy_of
    assert {parent_policy_of(i) for i in ctx.images} == {"pinned", "follow"}
    assert {image_policy_of(i) for i in ctx.instances} == {"pinned", "follow"}
    assert {bool(i.ephemeral) for i in ctx.instances} == {True, False}
    assert {s.state for s in ctx.storages} == {"active", "archived", "destroyed"}
    assert {rt.model.type_ for rt in ctx.runtime_builders.values()} == {"aws", "gcloud", "docker"}   # the container runtime too
    # the token says what the image IS; what it is treated as comes from the catalog
    assert {osb.model.get_vendor_family() for osb in ctx.os_builders.values()} == {"alma-linux", "debian", "ubuntu"}
    assert {osb.model.get_family() for osb in ctx.os_builders.values()} == {"rhel", "debian", "ubuntu"}
    assert {b.model.type_ for b in ctx.state_backends.values()} == {"s3", "local", "gcs"}
    assert any(getattr(g.model, "workload_connection", None) for g in ctx.group_builders.values())
    assert "okta" in {g.identity_type() for g in ctx.group_builders.values()}   # the Okta plugin, from the index
    assert (root / "meta-state" / "aliases.txt").is_file()
    assert any(i.get_name() == "gce-node" for i in ctx.instances)
