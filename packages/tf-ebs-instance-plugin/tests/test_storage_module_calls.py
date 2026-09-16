# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins module args and HCL rendering for the tf-aws storage builders."""
from types import SimpleNamespace
from typing import Any, cast

from cs_image_system.base.utils import render_module_call
from cs_image_system.tf_ebs_instance_plugin.tf_storage_builder import (
    TofuEfsStorageBuilder,
    TofuS3StorageBuilder,
)
from cs_image_system.tf_ebs_instance_plugin.tf_storage_models import (
    EbsVariables,
    EfsVariables,
    S3Variables,
    TofuEbsStorageBuilderModel,
)


def _builder(variables=None) -> Any:
    """A builder stand-in: ``module_args`` reads ``self.model.variables`` (stage 26)."""
    return SimpleNamespace(model=SimpleNamespace(variables=variables or EfsVariables()))


def _storage(name, *, tags=None, config=None, bucket_name=None) -> Any:
    return SimpleNamespace(
        get_name=lambda: name,
        tags=tags or {},
        config=config or {},
        bucket_name=bucket_name,
    )


def test_render_module_call_value_kinds():
    lines = render_module_call("m", "SRC", {
        "a_str": "plain",
        "a_ref": "module.other.id",
        "a_bool": True,
        "a_num": 42,
        "a_map": {"k": "v"},
    })
    hcl = "\n".join(lines)
    assert 'module "m" {' in hcl and hcl.endswith("}")
    assert 'source = "SRC"' in hcl
    assert 'a_str = "plain"' in hcl
    assert "a_ref = module.other.id" in hcl
    assert "a_bool = true" in hcl
    assert "a_num = 42" in hcl
    assert 'a_map = { "k" = "v" }' in hcl


def test_render_module_call_providers_meta_argument():
    lines = render_module_call("m", "SRC", {"name": "x"},
                               providers={"aws": "aws.open_tofu"})
    hcl = "\n".join(lines)
    # raw references on both sides, right after source
    assert "providers = { aws = aws.open_tofu }" in hcl
    assert hcl.index("source") < hcl.index("providers")


def test_s3_module_args_prefer_bucket_name():
    args = TofuS3StorageBuilder.module_args(
        cast(Any, _builder()), _storage("default-bucket", bucket_name="my-image-bucket",
                                    tags={"env": "production"}))
    assert args == {"bucket_name": "my-image-bucket", "tags": {"env": "production"}}


def test_s3_module_args_fall_back_to_storage_name():
    args = TofuS3StorageBuilder.module_args(cast(Any, _builder()), _storage("plain"))
    assert args == {"bucket_name": "plain"}


def test_efs_module_args_pass_existing_filesystem():
    args = TofuEfsStorageBuilder.module_args(
        cast(Any, _builder()), _storage("efs-storage", config={"file_system_id": "fs-12345678"}))
    assert args == {"name": "efs-storage", "existing_file_system_id": "fs-12345678"}


# ------------------------------------------------- variables (stage 26)

def test_declared_variables_reach_the_module_call_and_the_item_wins():
    """A builder's ``variables:`` are module inputs; what the item decides
    (name, existing filesystem, groups) is never overridden by them."""
    args = TofuEfsStorageBuilder.module_args(
        cast(Any, _builder(EfsVariables(performance_mode="maxIO", encrypted=True))),
        _storage("efs-storage", config={"file_system_id": "fs-1"}))
    assert args["performance_mode"] == "maxIO" and args["encrypted"] is True
    assert args["name"] == "efs-storage" and args["existing_file_system_id"] == "fs-1"


def test_undeclared_variables_are_absent_so_the_module_default_applies():
    args = TofuS3StorageBuilder.module_args(cast(Any, _builder(S3Variables())), _storage("b"))
    assert "force_destroy" not in args and "tags" not in args


def test_tags_merge_with_the_items_over_the_builders():
    args = TofuS3StorageBuilder.module_args(
        cast(Any, _builder(S3Variables(tags={"Project": "P", "env": "builder"}))),
        _storage("b", tags={"env": "item"}))
    assert args["tags"] == {"Project": "P", "env": "item"}


def test_variables_are_typed_per_provider():
    """The module's own variable names, exactly: the fixture's old
    `performance-mode` (hyphen) is refused rather than silently dropped."""
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="performance-mode"):
        EfsVariables(**{"performance-mode": "generalPurpose"})   # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        EbsVariables(**{"size": 8})   # type: ignore[arg-type]   size is the builder's own field


def test_parameters_is_refused_with_the_replacement_named():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="retired .stage 26.*variables"):
        TofuEbsStorageBuilderModel(name="aws-ebs", type_="tf-aws-ebs", runtime="r",
                                   parameters={"volume_type": "gp2"})   # type: ignore[call-arg]
