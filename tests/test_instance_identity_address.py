# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""An AWS runtime's identity of a machine carries its private address, which
a recorded server registry keeps beside the provider id and the hostname
(spec 010, FR-010); a machine with none answers an empty address."""
from __future__ import annotations

import pytest
from harness import FixtureRun


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    run = FixtureRun(tmp_path, monkeypatch)
    try:
        yield run.ctx.runtime_builders["aws-east2-runtime"]
    finally:
        run.restore_cwd()


def test_the_identity_carries_the_private_address(runtime, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    found = {"InstanceId": "i-0abc", "PrivateDnsName": "ip-10-1-2-3.ec2.internal", "PrivateIpAddress": "10.1.2.3"}
    monkeypatch.setattr(AwsCloudBuilder, "_named_instance", lambda self, name: dict(found) if name == "test" else None)
    assert runtime.query_instance_identity("test") == {
        "instance_id": "i-0abc", "provider_hostname": "ip-10-1-2-3.ec2.internal", "address": "10.1.2.3"}
    found.pop("PrivateIpAddress")
    assert runtime.query_instance_identity("test")["address"] == ""
    assert runtime.query_instance_identity("absent") is None
