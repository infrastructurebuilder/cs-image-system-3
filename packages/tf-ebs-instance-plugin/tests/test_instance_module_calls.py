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


def _s3(name="s3-east2", bucket="b", key_prefix="statefiles/", is_default=True):
    from cs_image_system.hashicorp_utils.collector import BackendRegistration
    from cs_image_system.tf_s3_state_plugin.tf_s3_state_models import S3_KIND
    return BackendRegistration(name=name, type="s3", kind=S3_KIND, is_default=is_default,
                               settings={"bucket": bucket, "region": "us-east-2", "key_prefix": key_prefix,
                                         "encrypt": False, "use_lockfile": True, "profile": None})


def _instance(name, image):
    return SimpleNamespace(get_name=lambda: name, image=image, get_tags=lambda: {"stype": "test"})


def _rtb(name="aws-east2-runtime", subnet="subnet-01"):
    networking = SimpleNamespace(default_subnet_id=subnet)
    return SimpleNamespace(
        get_name=lambda: name,
        get_default_machine_type=lambda: "t3.large",
        model=SimpleNamespace(networking=networking),
    )



def _services():
    """The one service each of these calls reaches: a lineage
    that labels nothing (a stand-in without a run gets no configuration id)
    and a scope every root is in."""
    return SimpleNamespace(
        lineage=SimpleNamespace(config_tags=lambda: {}, pinned_instance_build=lambda instance: None,
                                configuration_tag=lambda: ""),
        scope=SimpleNamespace(root_in_runtime_scope=lambda runtime: True,
                              apply_enabled=lambda key, root=None, aliases=(): True))


def _ctx(psi):
    return SimpleNamespace(get_provider_specific_image=lambda source, runtime: psi, services=_services())


def _module_args(psi):
    stub = SimpleNamespace(_image_var=TofuInstanceBuilder._image_var)
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

    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.hashicorp_utils.collector import terraform_collector
    from harness import bare_run

    run = bare_run(config={"use_state_backends": True})     # the collector lives with the run
    col = terraform_collector(run)
    stub = SimpleNamespace(
        name="open-tofu",
        get_path_for_phase=lambda phase, suffix: Path(
            f"open-tofu/{phase.value}/open-tofu-{phase.value}{suffix}"),
        _get_context=lambda: run,
    )
    for m in ("_backend_config_path", "_collector", "_context", "_init_args"):
        setattr(stub, m, getattr(TofuInstanceBuilder, m).__get__(stub))
    phase = ExecutionLifecyclePhase.INSTANCE_GENERATION

    # No backend bound: bare init.
    assert stub._init_args(phase) == ["init"]

    col.register_backend(_s3())
    col.set_backend("open-tofu", "s3-east2")
    assert stub._init_args(phase) == [
        "init",
        "-reconfigure", "-backend-config=open-tofu-instance-generation.tfbackend.hcl"]


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
    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    from pathlib import Path

    psi = GenericProviderSpecificImage.resolved(
        source_name="imgfile-basic-dask", source_kind=PSISourceKind.IMAGE,
        runtime="aws-east2-runtime", identifier="ami-0bbb")
    ctx = SimpleNamespace(
        get_provider_specific_image=lambda source, runtime: psi,
        generation_path=Path(tmp_path),
        services=_services(),
    )
    stub = SimpleNamespace(
        _instances=[_instance("test2", "imgfile-basic-dask")],
        _get_context=lambda: ctx,
        _runtime_builder=lambda: _rtb(),
        _image_var=TofuInstanceBuilder._image_var,
        get_path_for_phase=lambda phase, suffix: Path("open-tofu/instance-generation") / f"x{suffix}",
        # the hook checks the root's runtime against the run's scope
        model=SimpleNamespace(get_runtime_provider=lambda: "aws-east2-runtime"),
    )
    TofuInstanceBuilder.pre_finalize_phase(cast(Any, stub), ExecutionLifecyclePhase.INSTANCE_GENERATION)
    tfvars = tmp_path / "open-tofu/instance-generation/instances.auto.tfvars"
    assert tfvars.is_file()
    assert 'test2_ami_id = "ami-0bbb"' in tfvars.read_text()
