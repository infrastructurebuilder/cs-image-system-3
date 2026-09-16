# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0



# AWS_EBS_SOURCE_TYPE: str = "amazon-ebs"
# @dataclass(kw_only=True)
# class AwsEbsSourceConfig(SourceModel):
#     """AWS EBS Source configuration data object."""

#     # type: str = "aws-ebs"
#     # region: str.  Region comes from the cloud config
#     #  root-device-type assumed to be "ebs" and  virtualization-type
#     #   to be "hvm" for this type
#     instance_type: str = DEFAULT
#     owners: list[str] = field(default_factory=list)
#     filters: dict[str, str] = field(default_factory=dict)
#     most_recent: bool = True
