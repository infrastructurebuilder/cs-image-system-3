# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene XII item 33: the performing run's state query runs as the WRITE
role, which could not read a bucket's tags. The write role now carries the
read document as a second policy, and the state query marks a permission
refusal as REFUSED, a role's gap, not a cloud that did not answer."""
from __future__ import annotations

from tests.test_v2_bootstrap import EXAMPLES, REPO

from cs_image_system.base import state_query as sq


def test_the_write_role_carries_the_read_document_in_every_copy():
    for path in [REPO / "tfmodules" / "bootstrap_aws" / "main.tf"] + [
            EXAMPLES / n / "tfmodules" / "bootstrap_aws" / "main.tf" for n in ("complete", "standard-aws", "standard-aws-posix", "standard-gce")]:
        module = path.read_text()
        assert module.count("local.read_document") == 2, path                      # on both roles
        assert 'resource "aws_iam_role_policy" "write_reads"' in module and '"cs-image-system-write-reads"' in module, path
        assert 'resource "aws_iam_role_policy" "write_reads" {\n  name   = "cs-image-system-write-reads"\n  role   = aws_iam_role.write.id' in module, path
        assert module.count('"StorageReality"') == 1 and module.count('"Describe"') == 1   # one document, defined once
    guide = (EXAMPLES / "standard-aws" / "CI_SETUP.md").read_text()
    assert "cs-image-system-write-reads" in guide and "`REFUSED`" in guide


def test_a_permission_refusal_is_marked_as_such_in_the_report():
    report = sq.StateReport(run="r")
    denied = Exception("An error occurred (AccessDenied) when calling the GetBucketTagging operation: User: "
                       "arn:aws:sts::1:assumed-role/csis-github-apply/GitHubActions is not authorized to perform: "
                       "s3:GetBucketTagging on resource: \"arn:aws:s3:::b\"")

    def boom():
        raise denied
    assert sq._query(report, "storages/aws-s3", boom) is None
    assert report.unavailable == [f"storages/aws-s3: {sq.REFUSED} {denied}"]
    assert "csis-github-apply" in report.unavailable[0] and "GetBucketTagging" in report.unavailable[0]
    # a cloud that did not answer is still just that
    report = sq.StateReport(run="r")

    def timeout():
        raise Exception("Read timed out. (read timeout=60)")
    sq._query(report, "storages/pd", timeout)
    assert report.unavailable == ["storages/pd: Read timed out. (read timeout=60)"]
    assert "REFUSED" not in report.render()
    # botocore's shape: the code, not only the text
    class ClientErrorLike(Exception):
        response = {"Error": {"Code": "UnauthorizedOperation", "Message": "no"}}
    assert sq.is_refusal(ClientErrorLike("You are not allowed")) and not sq.is_refusal(ValueError("no such bucket"))
