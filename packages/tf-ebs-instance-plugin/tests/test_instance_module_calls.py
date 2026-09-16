# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins the PSI-backed AMI wiring in the tofu instance builder's module args."""
from types import SimpleNamespace
from typing import Any, cast

from cs_image_system.base.models.provider_specific_image import (
    GenericProviderSpecificImage,
    PSISourceKind,
)
from cs_image_system.tf_ebs_instance_plugin.tf_instance_builder import TofuInstanceBuilder


def _instance(name, image):
    return SimpleNamespace(get_name=lambda: name, image=image, get_tags=lambda: {"stype": "test"})


def _rtb(name="aws-east2-runtime", subnet="subnet-01"):
    networking = SimpleNamespace(default_subnet_id=subnet)
    return SimpleNamespace(
        get_name=lambda: name,
        get_default_machine_type=lambda: "t3.large",
        model=SimpleNamespace(networking=networking),
    )


def _ctx(psi):
    return SimpleNamespace(get_provider_specific_image=lambda source, runtime: psi)


def _module_args(psi):
    stub = SimpleNamespace(_ami_var=TofuInstanceBuilder._ami_var)
    return TofuInstanceBuilder._module_args(
        cast(Any, stub), _ctx(psi), _rtb(), cast(Any, _instance("test2", "basic-dask")))


def test_resolved_psi_yields_concrete_ami_id():
    psi = GenericProviderSpecificImage.resolved(
        source_name="basic-dask", source_kind=PSISourceKind.IMAGE,
        runtime="aws-east2-runtime", identifier="ami-0abc")
    args = _module_args(psi)
    assert args["ami_id"] == "ami-0abc"
    assert "ami_name_pattern" not in args
    assert args["instance_type"] == "t3.large"
    assert args["subnet_id"] == "subnet-01"
    assert args["tags"] == {"stype": "test"}


def test_deferred_psi_yields_name_pattern():
    psi = GenericProviderSpecificImage.deferred(
        source_name="basic-dask", source_kind=PSISourceKind.IMAGE,
        runtime="aws-east2-runtime", deferred_name_pattern="basic-dask-pckr-ebs-ans")
    args = _module_args(psi)
    assert args["ami_name_pattern"] == "basic-dask-pckr-ebs-ans*"
    # ami_id is a variable reference (empty until finalization fills it)
    assert args["ami_id"] == "var.test2_ami_id" 


def test_missing_psi_omits_ami_args():
    args = _module_args(None)
    assert "ami_id" not in args and "ami_name_pattern" not in args


def test_init_args_carry_backend_config_when_enabled(monkeypatch):
    """Partial backend configuration: init must pass -backend-config=<file>."""
    from pathlib import Path

    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.hashicorp_utils.collector import (
        BackendRegistration,
        TerraformCollector,
    )

    col = TerraformCollector()
    col.reset()
    try:
        stub = SimpleNamespace(
            name="open-tofu",
            get_path_for_phase=lambda phase, suffix: Path(
                f"open-tofu/{phase.value}/open-tofu-{phase.value}{suffix}"),
        )
        stub._backend_config_path = (
            TofuInstanceBuilder._backend_config_path.__get__(stub))
        stub._init_args = TofuInstanceBuilder._init_args.__get__(stub)
        phase = ExecutionLifecyclePhase.INSTANCE_GENERATION

        # No backend bound (or backends gated off): bare init.
        assert stub._init_args(phase) == ["init"]

        monkeypatch.setattr(TerraformCollector(), "backends_enabled", lambda: True)
        col.register_backend(BackendRegistration(
            name="s3-east2", type="s3", bucket="b", region="us-east-2",
            key_prefix="statefiles/", is_default=True))
        col.set_backend("open-tofu", "s3-east2")
        assert stub._init_args(phase) == [
            "init",
            "-reconfigure", "-backend-config=open-tofu-instance-generation.tfbackend.hcl"]
    finally:
        col.reset()


def test_deferred_psi_also_wires_ami_variable():
    psi = GenericProviderSpecificImage.deferred(
        source_name="basic-dask", source_kind=PSISourceKind.IMAGE,
        runtime="aws-east2-runtime", deferred_name_pattern="basic-dask-pckr-ebs-ans")
    args = _module_args(psi)
    # finalization fills var.test2_ami_id from the packer manifest; the
    # name-pattern remains the in-module fallback while it is empty.
    assert args["ami_id"] == "var.test2_ami_id"
    assert args["ami_name_pattern"] == "basic-dask-pckr-ebs-ans*"


def test_pre_finalize_writes_tfvars_for_resolved_psis(tmp_path):
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from pathlib import Path

    psi = GenericProviderSpecificImage.resolved(
        source_name="imgfile-basic-dask", source_kind=PSISourceKind.IMAGE,
        runtime="aws-east2-runtime", identifier="ami-0bbb")
    ctx = SimpleNamespace(
        get_provider_specific_image=lambda source, runtime: psi,
        generation_path=Path(tmp_path),
    )
    stub = SimpleNamespace(
        _instances=[_instance("test2", "imgfile-basic-dask")],
        _get_context=lambda: ctx,
        _runtime_builder=lambda: _rtb(),
        _ami_var=TofuInstanceBuilder._ami_var,
        get_path_for_phase=lambda phase, suffix: Path("open-tofu/instance-generation") / f"x{suffix}",
    )
    TofuInstanceBuilder.pre_finalize_phase(cast(Any, stub), ExecutionLifecyclePhase.INSTANCE_GENERATION)
    tfvars = tmp_path / "open-tofu/instance-generation/instances.auto.tfvars"
    assert tfvars.is_file()
    assert 'test2_ami_id = "ami-0bbb"' in tfvars.read_text()
