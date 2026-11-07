# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins the PackerCollector: plugin merge/conflict and golden blocks."""
import pytest

from harness import bare_run

from cs_image_system.hashicorp_utils.collector import PackerCollector, PackerVariableDecl, packer_collector
from cs_image_system.hashicorp_utils.versions import HclConfigConflictError


@pytest.fixture
def col():
    return PackerCollector()


def test_a_packer_collector_lives_with_its_run():
    """One per run context, made on the first ask; another run's holds
    nothing of it."""
    a, b = bare_run(), bare_run()
    packer_collector(a).require_plugin("ws", "amazon", source="github.com/hashicorp/amazon")
    assert packer_collector(a) is packer_collector(a)
    assert [p.name for p in packer_collector(a).merged_plugins("ws")] == ["amazon"]
    assert packer_collector(b) is not packer_collector(a) and packer_collector(b).merged_plugins("ws") == []


def test_merge_across_registrations(col):
    col.require_plugin("pckr-ebs-ans", "amazon",
                       source="github.com/hashicorp/amazon", version=">= 1.0.0")
    col.require_plugin("pckr-ebs-ans", "amazon",
                       source="github.com/hashicorp/amazon", version=">= 1.0.0")
    merged = col.merged_plugins("pckr-ebs-ans")
    assert len(merged) == 1 and merged[0].version == ">= 1.0.0"


def test_conflict_aborts(col):
    col.require_plugin("a", "amazon", version="== 1.0.0")
    col.require_plugin("b", "amazon", version="== 2.0.0")
    with pytest.raises(HclConfigConflictError):
        col.generate_packer_block("a")


def test_golden_packer_block(col):
    col.require_plugin("ws", "amazon",
                       source="github.com/hashicorp/amazon", version=">= 1.0.0")
    hcl = "\n".join(col.generate_packer_block("ws"))
    assert "packer {" in hcl
    assert "required_plugins {" in hcl
    assert "amazon" in hcl and '">= 1.0.0"' in hcl and "github.com/hashicorp/amazon" in hcl


def test_variable_blocks(col):
    col.declare_variable("ws", PackerVariableDecl(
        name="release", type="bool", default=True, description="immutable?"))
    col.declare_variable("ws", PackerVariableDecl(
        name="base_image_version", type="string", env_var="BASE_IMAGE_VERSION",
        default="1.0.0"))
    hcl = "\n".join(col.generate_variable_blocks("ws"))
    assert 'variable "release"' in hcl and "bool" in hcl
    assert 'variable "base_image_version"' in hcl and 'env("BASE_IMAGE_VERSION")' in hcl
