# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins TerraformRootMixin: backend path, init args, command materialization."""
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from cs_image_system.hashicorp_utils.collector import (
    terraform_collector,
)
from cs_image_system.hashicorp_utils.testing import bare_run
from cs_image_system.tofu_roots.roots import TerraformRootMixin


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
