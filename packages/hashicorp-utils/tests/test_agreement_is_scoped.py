# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""One provider's roots never fail for another provider's declarations.

Two workspaces that disagree about a provider (or a packer plugin) is an
error for the workspaces that declare it. A third workspace that does not
declare it still emits: the disagreement is not its own. The run-wide form
of the check, asked with no workspace, still sees everything.
"""
from __future__ import annotations

import pytest

from cs_image_system.hashicorp_utils.collector import PackerCollector, TerraformCollector
from cs_image_system.hashicorp_utils.versions import HclConfigConflictError


@pytest.fixture
def roots() -> TerraformCollector:
    col = TerraformCollector()
    col.require_provider("one", "shared", source="vendor/shared", version="== 4.0.0")
    col.require_provider("two", "shared", source="vendor/shared", version="== 5.0.0")
    col.require_provider("apart", "own", source="vendor/own", version=">= 1.0.0")
    return col


def test_a_root_that_does_not_declare_the_disputed_provider_still_emits(roots: TerraformCollector):
    assert "vendor/own" in "\n".join(roots.generate_terraform_block("apart"))
    roots.generate_provider_blocks("apart")
    roots.generate_variable_blocks("apart")


@pytest.mark.parametrize("workspace", ["one", "two"])
def test_each_root_that_declares_it_fails_and_the_dispute_is_named(roots: TerraformCollector, workspace: str):
    with pytest.raises(HclConfigConflictError) as refused:
        roots.generate_terraform_block(workspace)
    assert "shared" in str(refused.value) and "one" in str(refused.value) and "two" in str(refused.value)


def test_the_run_wide_check_still_sees_every_dispute(roots: TerraformCollector):
    with pytest.raises(HclConfigConflictError):
        roots.validate_all()


def test_a_dispute_over_the_source_is_scoped_the_same_way():
    col = TerraformCollector()
    col.require_provider("one", "shared", source="vendor/shared", version=">= 1.0.0")
    col.require_provider("two", "shared", source="elsewhere/shared", version=">= 1.0.0")
    col.require_provider("apart", "own", source="vendor/own", version=">= 1.0.0")
    col.generate_terraform_block("apart")
    with pytest.raises(HclConfigConflictError, match="different sources"):
        col.generate_terraform_block("one")


def test_the_packer_plugins_are_scoped_the_same_way():
    col = PackerCollector()
    col.require_plugin("one", "shared", version="== 1.0.0")
    col.require_plugin("two", "shared", version="== 2.0.0")
    col.require_plugin("apart", "own", source="vendor/own", version=">= 1.0.0")
    assert "own" in "\n".join(col.generate_packer_block("apart"))
    with pytest.raises(HclConfigConflictError):
        col.generate_packer_block("one")
    with pytest.raises(HclConfigConflictError):
        col.validate_all()


def test_the_collectors_are_kept_under_the_librarys_own_namespace():
    """A run keeps each collector beside its context under a key that
    carries this library's namespace, so no plugin's own state can meet it;
    the bare run refuses a key without one, as the core's context does."""
    from cs_image_system.hashicorp_utils import collector
    from cs_image_system.hashicorp_utils.testing import bare_run
    assert collector.TERRAFORM_COLLECTOR_KEY.startswith("hashicorp-utils/")
    assert collector.PACKER_COLLECTOR_KEY.startswith("hashicorp-utils/")
    run = bare_run()
    assert collector.terraform_collector(run) is collector.terraform_collector(run)
    with pytest.raises(ValueError, match="names no namespace"):
        run.plugin_state("terraform-collector", dict)


# ------------------------------------------------------------ state locations, scoped the same way

class _OneFilePerPrefix:
    """A backend kind for these tests: a workspace's state is the object
    ``<prefix>.tfstate`` in the backend's container, whatever the workspace
    is called, so two workspaces bound to one backend share a location."""

    def location(self, settings, workspace):
        from cs_image_system.contract.state import StateLocation
        return StateLocation("sample", str(settings["container"]), f"{settings['prefix']}.tfstate")

    def backend_settings(self, settings, workspace):
        return {"path": f"{settings['prefix']}.tfstate"}

    def remote_state_settings(self, settings, workspace):
        return {"path": f"{settings['prefix']}.tfstate"}


def _backend(name: str, prefix: str):
    from cs_image_system.contract.state import BackendRegistration
    return BackendRegistration(name=name, type="sample", settings={"container": "c", "prefix": prefix},
                               kind=_OneFilePerPrefix())


@pytest.fixture
def located() -> TerraformCollector:
    """Two roots bound to one state object, and a third bound to its own."""
    col = TerraformCollector()
    col.register_backend(_backend("shared", "shared"))
    col.register_backend(_backend("apart", "apart"))
    col.set_backend("one", "shared")
    col.set_backend("two", "shared")
    col.set_backend("third", "apart")
    return col


def test_a_root_that_shares_no_state_object_emits_while_two_others_collide(located: TerraformCollector):
    located.generate_terraform_block("third")
    located.generate_variable_blocks("third")


@pytest.mark.parametrize("workspace", ["one", "two"])
def test_each_root_whose_state_object_is_shared_is_refused_and_both_are_named(located: TerraformCollector, workspace: str):
    with pytest.raises(HclConfigConflictError) as refused:
        located.generate_terraform_block(workspace)
    assert "one, two" in str(refused.value) and "shared.tfstate" in str(refused.value)


def test_the_run_wide_check_still_sees_every_shared_state_object(located: TerraformCollector):
    with pytest.raises(HclConfigConflictError):
        located.validate_all()
    with pytest.raises(HclConfigConflictError):
        located.validate_state_locations()
