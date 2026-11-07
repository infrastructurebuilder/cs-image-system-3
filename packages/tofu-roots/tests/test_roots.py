# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins TerraformRootMixin: backend path, init args, command materialization."""
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from cs_image_system.hashicorp_utils.collector import (
    BackendRegistration,
    terraform_collector,
)
from cs_image_system.tofu_roots.roots import TerraformRootMixin
from harness import bare_run


def _s3(name="s3-east2", bucket="b", key_prefix="statefiles/", is_default=True):
    from cs_image_system.tf_s3_state_plugin.tf_s3_state_models import S3_KIND
    return BackendRegistration(name=name, type="s3", kind=S3_KIND, is_default=is_default,
                               settings={"bucket": bucket, "region": "us-east-2", "key_prefix": key_prefix,
                                         "encrypt": False, "use_lockfile": True, "profile": None})


class _Exe:
    """Minimal ExecutableModel stand-in: args/working_directory are mutated."""

    def __init__(self) -> None:
        self.args: list[str] = []
        self.working_directory: Path | None = None


def _phase(value: str = "user-generation"):
    return cast(Any, SimpleNamespace(value=value))


def _root(run: Any, name: str = "okta-tf-users") -> Any:
    """A root stub in ``run`` (a bare run context: the collector lives there)."""
    stub = SimpleNamespace(
        name=name,
        _get_context=lambda: run,
        get_path_for_phase=lambda phase, discriminator=None, suffix=None: (
            Path(name) / phase.value / f"{name}-{phase.value}{suffix or ''}"
        ),
        get_executable_copy=_Exe,
    )
    for m in ("_backend_config_path", "_collector", "_context", "_dry_run", "_init_args", "_runner_init_args",
              "terraform_commands"):
        setattr(stub, m, getattr(TerraformRootMixin, m).__get__(stub))
    return stub


def _root_in_run(run: Any, dry_run: bool, name: str = "okta-tf-users") -> Any:
    """A root whose run is dry or real, as every real builder can see."""
    run.dry_run = dry_run
    return _root(run, name)


@pytest.fixture
def run():
    """A bare run with backends enabled; its collector is ``col``."""
    return bare_run(config={"use_state_backends": True})


@pytest.fixture
def col(run):
    return terraform_collector(run)


def test_init_args_without_backend(run, col):
    assert _root(run)._init_args(_phase()) == ["init"]


def test_init_args_with_backend_uses_bare_filename(run, col):
    col.register_backend(_s3())
    col.set_backend("okta-tf-users", "s3-east2")
    args = _root(run)._init_args(_phase())
    assert args == ["init", "-reconfigure", "-backend-config=okta-tf-users-user-generation.tfbackend.hcl"]
    assert "/" not in args[1]  # tofu runs inside the phase dir


def test_a_dry_run_initialises_without_the_backend(run, col):
    """A dry run never touches remote state (it holds decrypted values):
    providers are installed and the emission validated with -backend=false,
    whether or not a backend is registered; a real run keeps the backend."""
    assert _root_in_run(run, dry_run=True)._init_args(_phase()) == ["init", "-backend=false"]
    col.register_backend(_s3())
    col.set_backend("okta-tf-users", "s3-east2")
    assert _root_in_run(run, dry_run=True)._init_args(_phase()) == ["init", "-backend=false"]
    assert _root_in_run(run, dry_run=False)._init_args(_phase()) == [
        "init", "-reconfigure", "-backend-config=okta-tf-users-user-generation.tfbackend.hcl"]


def test_the_runner_script_initialises_in_the_real_form_whatever_the_run_mode(run, col):
    """A committed run script inits its own root -- with the backend,
    reconfiguring (a dry run left a backend-less .terraform/, or a backend
    argument such as `encrypt` changed since) -- even when the run that
    wrote it was dry."""
    assert _root_in_run(run, dry_run=True)._runner_init_args(_phase()) == ["init", "-input=false", "-reconfigure"]
    col.register_backend(_s3())
    col.set_backend("okta-tf-users", "s3-east2")
    for dry in (True, False):
        assert _root_in_run(run, dry_run=dry)._runner_init_args(_phase()) == [
            "init", "-input=false", "-reconfigure", "-backend-config=okta-tf-users-user-generation.tfbackend.hcl"]


def test_backend_config_path(run):
    p = _root(run)._backend_config_path(_phase())
    assert p == Path("okta-tf-users/user-generation/okta-tf-users-user-generation.tfbackend.hcl")


def test_terraform_commands_copies_per_command(run):
    root = _root(run)
    wd = Path("okta-tf-users/user-generation")
    cmds = root.terraform_commands(_phase(), [["fmt"], ["validate"], ["plan"]], wd)
    assert [c.args for c in cmds] == [["fmt"], ["validate"], ["plan"]]
    assert all(c.working_directory == wd for c in cmds)
    # distinct executable copies -- the shared-object bug class
    assert len({id(c) for c in cmds}) == 3
