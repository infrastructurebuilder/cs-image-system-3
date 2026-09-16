# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins the run-scoped TerraformCollector: registration, conflicts, generation."""
import pytest

from cs_image_system.hashicorp_utils.collector import (
    BackendRegistration,
    TerraformCollector,
    TerraformVariable,
)
from cs_image_system.hashicorp_utils.versions import HclConfigConflictError


@pytest.fixture
def col(monkeypatch):
    c = TerraformCollector()
    c.reset()
    monkeypatch.setattr(c, "backends_enabled", lambda: False)
    yield c
    c.reset()


@pytest.fixture
def backend():
    return BackendRegistration(
        name="s3-east2", type="s3", bucket="my-bucket", region="us-east-2",
        key_prefix="statefiles/csia/", encrypt=True, use_lockfile=True,
        profile="noaa", is_default=True)


def test_singleton_and_reset(col):
    assert TerraformCollector() is col
    col.require_provider("ws", "aws")
    col.reset()
    assert col.merged_providers("ws") == []


def test_workspace_isolation_and_dedupe(col):
    col.require_provider("a", "aws", source="hashicorp/aws", version=">= 4.0.0")
    col.require_provider("a", "aws", source="hashicorp/aws", version=">= 4.0.0")
    col.require_provider("b", "oktapam", source="okta/oktapam")
    a = col.merged_providers("a")
    assert len(a) == 1 and a[0].version == ">= 4.0.0"
    assert [p.name for p in col.merged_providers("b")] == ["oktapam"]


def test_merged_version_emission(col):
    col.require_provider("ws", "aws", source="hashicorp/aws", version=">= 4.0.0")
    col.require_provider("ws", "aws", source="hashicorp/aws", version="< 6.0.0")
    assert col.merged_providers("ws")[0].version == ">= 4.0.0, < 6.0.0"


def test_source_mismatch_aborts(col):
    col.require_provider("ws", "aws", source="hashicorp/aws")
    col.require_provider("ws", "aws", source="mycorp/aws")
    with pytest.raises(HclConfigConflictError, match="different sources"):
        col.merged_providers("ws")


def test_global_cross_workspace_conflict(col):
    col.require_provider("ws-one", "aws", source="hashicorp/aws", version="== 4.0.0")
    col.require_provider("ws-two", "aws", source="hashicorp/aws", version="== 5.0.0")
    # each workspace alone is fine...
    col.merged_providers("ws-one")
    # ...but generation runs the global check
    with pytest.raises(HclConfigConflictError, match="ws-one|ws-two"):
        col.generate_terraform_block("ws-one")


def test_generate_terraform_block_golden(col):
    col.require_provider("ws", "aws", source="hashicorp/aws", version=">= 4.0.0")
    hcl = "\n".join(col.generate_terraform_block("ws"))
    assert "terraform {" in hcl
    assert "required_providers {" in hcl
    assert 'source = "hashicorp/aws"' in hcl.replace("  ", " ").replace("   ", " ") or \
           '"hashicorp/aws"' in hcl
    assert '">= 4.0.0"' in hcl
    assert "backend" not in hcl  # gated off


def test_backend_block_when_enabled_is_partial(col, backend, monkeypatch):
    """The terraform block carries only an EMPTY backend block (partial
    configuration); the settings live in the .tfbackend.hcl file."""
    monkeypatch.setattr(col, "backends_enabled", lambda: True)
    col.register_backend(backend)
    col.require_provider("open-tofu", "aws", source="hashicorp/aws")
    col.set_backend("open-tofu", "s3-east2")
    hcl = "\n".join(col.generate_terraform_block("open-tofu"))
    assert 'backend "s3"' in hcl
    assert "bucket" not in hcl and "statefiles" not in hcl and "noaa" not in hcl


def test_backend_config_file_contents(col, backend, monkeypatch):
    monkeypatch.setattr(col, "backends_enabled", lambda: True)
    col.register_backend(backend)
    col.set_backend("open-tofu", "s3-east2")
    lines = col.generate_backend_config("open-tofu")
    body = "\n".join(lines)
    assert 'bucket = "my-bucket"' in body
    assert 'key = "statefiles/csia/open_tofu.tfstate"' in body
    assert 'region = "us-east-2"' in body
    assert "encrypt = true" in body and "use_lockfile = true" in body
    assert 'profile = "noaa"' in body


def test_backend_config_empty_when_gated_off_or_unbound(col, backend, monkeypatch):
    col.register_backend(backend)
    col.set_backend("open-tofu", "s3-east2")
    assert col.generate_backend_config("open-tofu") == []  # gated off
    monkeypatch.setattr(col, "backends_enabled", lambda: True)
    assert col.generate_backend_config("never-bound") == []  # no backend bound


def test_default_backend_resolution(col, backend):
    col.register_backend(backend)
    assert col.resolve_backend(None) is backend
    assert col.resolve_backend("default") is backend
    assert col.resolve_backend("s3-east2") is backend


def test_duplicate_backend_conflict(col, backend):
    col.register_backend(backend)
    col.register_backend(backend)  # identical: fine
    from dataclasses import replace
    with pytest.raises(HclConfigConflictError, match="registered twice"):
        col.register_backend(replace(backend, bucket="other-bucket"))


def test_remote_state_datasource_when_enabled(col, backend, monkeypatch):
    monkeypatch.setattr(col, "backends_enabled", lambda: True)
    col.register_backend(backend)
    col.set_backend("aws-ebs", "s3-east2")
    col.reference_remote_state("open-tofu", producer_workspace="aws-ebs")
    hcl = "\n".join(col.generate_remote_state_datasources("open-tofu"))
    assert 'data "terraform_remote_state" "aws_ebs"' in hcl
    assert '"s3"' in hcl
    assert '"statefiles/csia/aws_ebs.tfstate"' in hcl


def test_remote_state_empty_when_gated_off(col, backend):
    col.register_backend(backend)
    col.reference_remote_state("open-tofu", producer_workspace="aws-ebs")
    assert col.generate_remote_state_datasources("open-tofu") == []


def test_variable_redefinition_conflict(col):
    v = TerraformVariable(name="x", type="string", default="")
    col.declare_variable("ws", v)
    col.declare_variable("ws", TerraformVariable(name="x", type="string", default=""))
    with pytest.raises(HclConfigConflictError, match="redefined"):
        col.declare_variable("ws", TerraformVariable(name="x", type="number"))


def test_provider_config_and_variable_generation(col):
    col.require_provider("ws", "aws", source="hashicorp/aws")
    col.configure_provider("ws", "aws", {"region": "us-east-2", "profile": "noaa"})
    col.declare_variable("ws", TerraformVariable(name="test2_ami_id", type="string", default=""))
    phcl = "\n".join(col.generate_provider_blocks("ws"))
    assert 'provider "aws"' in phcl and '"us-east-2"' in phcl and '"noaa"' in phcl
    # alias auto-derived from the workspace so aggregated blocks cannot collide
    assert 'alias = "ws"' in phcl
    vhcl = "\n".join(col.generate_variable_blocks("ws"))
    assert 'variable "test2_ami_id"' in vhcl and "string" in vhcl


def test_provider_alias_and_bindings(col):
    col.configure_provider("open-tofu", "aws", {"region": "us-east-2"})
    assert col.provider_bindings("open-tofu") == {"aws": "aws.open_tofu"}
    phcl = "\n".join(col.generate_provider_blocks("open-tofu"))
    assert 'alias = "open_tofu"' in phcl


def test_explicit_alias_overrides_derived(col):
    col.configure_provider("ws", "aws", {"region": "us-east-2"}, alias="custom")
    assert col.provider_bindings("ws") == {"aws": "aws.custom"}
    assert 'alias = "custom"' in "\n".join(col.generate_provider_blocks("ws"))
