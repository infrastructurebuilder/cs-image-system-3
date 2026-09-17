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


# ------------------------------------------------------------- stage 46

def test_a_state_location_is_the_normalised_tuple():
    """The operator's table: A and B differ by bucket, C normalises to
    BUCKET1/xyz, D collides with C; plus the empty prefix, a prefix without a
    trailing slash, a prefix that is only slashes, and a refused segment."""
    from cs_image_system.hashicorp_utils.collector import StateLocation
    a = StateLocation.of("s3", "BUCKET1", "abc", "p")
    b = StateLocation.of("s3", "BUCKET2", "xyz", "p")
    c = StateLocation.of("s3", "BUCKET1", "//xyz", "p")
    d = StateLocation.of("s3", "BUCKET1", "xyz/", "p")
    assert len({a, b, c, d}) == 3 and c == d and a != c and b != c
    assert c.key == "xyz/p.tfstate" and str(c) == "s3://BUCKET1/xyz/p.tfstate"
    assert StateLocation.of("s3", "b", "", "ws").key == "ws.tfstate"
    assert StateLocation.of("s3", "b", "a/b", "ws").key_prefix == "a/b"
    assert StateLocation.of("s3", "b", "///", "ws").key == "ws.tfstate"
    assert StateLocation.of("s3", "b", "Statefiles/CSIA", "ws").key_prefix == "Statefiles/CSIA"   # case kept
    with pytest.raises(ValueError, match=r"'\.\.'"):
        StateLocation.of("s3", "b", "a/../b", "ws")
    assert TerraformCollector().state_collisions({"C": c, "D": d, "A": a}) == \
        ["workspaces C, D would share the state object s3://BUCKET1/xyz/p.tfstate"]


def test_the_emitted_key_is_normalised(col, monkeypatch):
    monkeypatch.setattr(col, "backends_enabled", lambda: True)
    col.register_backend(BackendRegistration(name="odd", type="s3", bucket="b", region="us-east-2",
                                             key_prefix="statefiles//x/", is_default=True))
    col.set_backend("open-tofu", "odd")
    assert 'key = "statefiles/x/open_tofu.tfstate"' in "\n".join(col.generate_backend_config("open-tofu"))


def test_a_rebinding_to_a_different_backend_is_refused(col, backend):
    from dataclasses import replace
    col.register_backend(backend)
    col.register_backend(replace(backend, name="s3-east1", bucket="other", is_default=False))
    col.set_backend("open-tofu", "s3-east2")
    col.set_backend("open-tofu", "s3-east2")          # the same one: a no-op
    with pytest.raises(HclConfigConflictError, match="'open-tofu' is bound to state backend 's3-east2'.*'s3-east1'"):
        col.set_backend("open-tofu", "s3-east1")


def test_the_chain_is_own_value_then_runtime_then_default(col, backend):
    from dataclasses import replace
    col.register_backend(backend)
    col.register_backend(replace(backend, name="s3-east1", bucket="other", is_default=False))
    assert col.effective_backend_name("s3-east1", "s3-east2") == "s3-east1"     # the builder names one
    assert col.effective_backend_name("default", "s3-east1") == "s3-east1"      # else its runtime's
    assert col.effective_backend_name(None, "self") == "default"                 # else the default
    assert col.bind_workspace("ws", "", None) == "default"
    assert col.workspace_backend("ws") is None or col._workspace_backend_registration("ws").name == "s3-east2"


def test_two_names_that_collapse_or_two_backends_on_one_prefix_are_refused(col, backend):
    from dataclasses import replace
    col.register_backend(backend)
    col.set_backend("aws-ebs", "s3-east2")
    col.set_backend("aws_ebs", "s3-east2")             # super_safe_name collapses both to aws_ebs
    with pytest.raises(HclConfigConflictError, match="aws-ebs, aws_ebs would share the state object"):
        col.validate_state_locations()
    col.reset()
    col.register_backend(backend)
    col.register_backend(replace(backend, name="twin", key_prefix="statefiles//csia", is_default=False))
    col.set_backend("one", "s3-east2")
    col.set_backend("one", "s3-east2")
    col.set_backend("two", "twin")
    assert col.state_collisions(col.state_locations()) == []           # different objects: one.tfstate, two.tfstate
    col.set_backend("one_", "twin")                                    # hmm: one_ -> one_.tfstate; no collision
    col.validate_state_locations()


def test_a_cross_backend_read_carries_the_producers_backend(col, backend, monkeypatch):
    """A consumer in backend A referencing a producer in backend B emits a
    remote-state datasource with B's bucket, key and region; an explicit
    backend_name on the reference overrides the producer's binding."""
    from dataclasses import replace
    monkeypatch.setattr(col, "backends_enabled", lambda: True)
    east1 = replace(backend, name="s3-east1", bucket="east1-bucket", region="us-east-1",
                    key_prefix="statefiles/csia/", profile=None, is_default=False)
    col.register_backend(backend)
    col.register_backend(east1)
    col.set_backend("aws-ebs", "s3-east1")             # the producer, in B
    col.set_backend("open-tofu", "s3-east2")           # the consumer, in A
    col.reference_remote_state("open-tofu", producer_workspace="aws-ebs")
    hcl = "\n".join(col.generate_remote_state_datasources("open-tofu"))
    assert 'bucket = "east1-bucket"' in hcl and 'key = "statefiles/csia/aws_ebs.tfstate"' in hcl
    assert 'region = "us-east-1"' in hcl and "noaa" not in hcl
    own = "\n".join(col.generate_backend_config("open-tofu"))
    assert 'bucket = "my-bucket"' in own                              # its own state stays in A
    col.reset(); monkeypatch.setattr(col, "backends_enabled", lambda: True)
    col.register_backend(backend); col.register_backend(east1)
    col.set_backend("aws-ebs", "s3-east1")
    col.reference_remote_state("open-tofu", producer_workspace="aws-ebs", backend_name="s3-east2")
    hcl = "\n".join(col.generate_remote_state_datasources("open-tofu"))
    assert 'bucket = "my-bucket"' in hcl and 'region = "us-east-2"' in hcl


def test_the_backend_record_carries_what_a_migration_needs(col, backend, monkeypatch):
    monkeypatch.setattr(col, "backends_enabled", lambda: True)
    col.register_backend(backend)
    col.set_backend("open-tofu", "s3-east2")
    rec = col.backend_record("open-tofu")
    assert rec == {"backend": "s3-east2", "type": "s3", "bucket": "my-bucket",
                   "key": "statefiles/csia/open_tofu.tfstate", "region": "us-east-2",
                   "encrypt": True, "use_lockfile": True, "profile": "noaa"}
    assert col.backend_record("never-bound") is None
