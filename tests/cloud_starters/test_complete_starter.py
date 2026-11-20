# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The ``complete`` starter, with every provider installed.

``complete`` declares every provider, the Google Cloud family's among them,
and that family is released from its own repository: this workspace's venv
does not hold it, so ``tests/test_docs_examples.py`` cannot load the tree.
These tests can: ``just test-cloud-starters`` runs them with the family
layered in from the index by the ``gcloud`` extra's ranges (spec 005,
research R11). The default collection leaves this directory out
(``norecursedirs`` in ``pyproject.toml``), and the recipe runs it under the
strict session, so a missing family fails instead of skipping.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from harness import FIXED_CHECKED_AT, load_context, record_network_facts, stub_environment
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


def _complete(tmp_path: Path, monkeypatch, rendered_starters: Path, overlays: tuple[str, ...] = ()):
    stub_environment(monkeypatch)
    root = copy_example(tmp_path, "complete", rendered_starters)
    stub_networks_from(monkeypatch, root)
    _gcloud(monkeypatch, root)
    stub_opa_credentials_from(monkeypatch, root)
    ctx = load_context(root, dry_run=True, overlays=[root / "overlays" / f"{o}.yaml" for o in overlays])
    return root, ctx


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
    assert (root / "meta-state" / "aliases.txt").is_file()
    assert any(i.get_name() == "gce-node" for i in ctx.instances)
