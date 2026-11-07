# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 17: credentials are a declared object, not an opaque mapping.

The gap this closes was measured twice before it was fixed: forbidding
unknown keys (stage 21) cannot reach inside a field typed as a plain
mapping, so `profile_nme: noaa` stayed silent and the profile silently
became None -- falling back to AWS_PROFILE, or to no profile at all.
"""
from __future__ import annotations

import pytest

from cs_image_system.base.loader import load_plugins
from cs_image_system.base.models.credentials import CredentialsBase


def _aws_model():
    load_plugins()
    from cs_image_system.aws_runtime.aws_runtime_models import AwsCloudBuilderModel
    return AwsCloudBuilderModel


def _converter():
    load_plugins()
    from cs_image_system.base.orchestrator import Orchestrator
    return Orchestrator().get_converter()


def _base(name: str) -> dict:
    """The registry is a process-wide singleton and refuses a duplicate name,
    so each test declares its own runtime."""
    return {"name": name, "type": "aws", "region": "us-east-2",
            "default_machine_type": "t3.micro"}


def test_declared_credentials_reach_the_model_and_convert_to_a_mapping():
    m = _converter().structure({**_base("cred-a"), "credentials": {"profile_name": "noaa"}}, _aws_model())
    assert m.credentials.profile_name == "noaa"
    # every consumer wants a mapping (boto3 kwargs, the --profile flag)
    assert m.get_credentials() == {"profile_name": "noaa"}


def test_a_typo_inside_credentials_is_an_error_naming_its_path():
    """The whole point of the stage: this was silent, and its consequence --
    no profile -- surfaced far away as an auth failure."""
    with pytest.raises(Exception) as exc:
        _converter().structure({**_base("cred-b"), "credentials": {"profile_nme": "noaa"}}, _aws_model())
    assert "profile_nme" in str(exc.value)
    assert "credentials" in str(exc.value)


def test_unset_fields_are_omitted_rather_than_passed_as_none():
    """A client library must not receive aws_access_key_id=None."""
    m = _converter().structure({**_base("cred-c"), "credentials": {"profile_name": "noaa"}}, _aws_model())
    assert m.get_credentials() == {"profile_name": "noaa"}
    assert "aws_access_key_id" not in m.get_credentials()


def test_absent_credentials_are_falsy_so_the_old_question_still_answers():
    """`if self.credentials:` asked "did the operator declare any?" of a dict;
    a dataclass instance is always truthy, so the base defines __bool__."""
    m = _converter().structure(_base("cred-d"), _aws_model())
    assert not m.credentials
    assert m.get_credentials() == {}
    assert not CredentialsBase()


def test_the_aws_client_config_passes_the_declared_values_through():
    m = _converter().structure({**_base("cred-e"), "credentials": {"profile_name": "noaa"}}, _aws_model())
    cfg = m.self_to_aws_client_config()
    assert cfg["profile_name"] == "noaa"
    assert cfg["region_name"] == "us-east-2"


def test_a_runtime_needing_no_declaration_still_works():
    """GCE authenticates with Application Default Credentials and declares
    nothing; the base class is the empty case, not a special case."""
    c = CredentialsBase()
    assert c.as_dict() == {} and not c
