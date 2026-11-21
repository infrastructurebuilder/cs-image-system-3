# Contract: the AWS family's repository

**Feature**: [spec.md](../spec.md) | **Decisions**:
[research.md](../research.md) R1, R3, R4, R11

The AWS family's repository keeps the contract the Google Cloud family's
does, word for word but for the names:
[specs/005-relocate-gcp-provider/contracts/family-repository.md](../../005-relocate-gcp-provider/contracts/family-repository.md)
(its lifecycle targets, what a package declares, CI, what an operator
types). What differs:

| Item | The AWS family's |
| --- | --- |
| Repository | `infrastructurebuilder/cs-image-system-aws`, work on `develop` |
| Distributions | `cs-image-system-aws-runtime-plugin`, `cs-image-system-tf-ebs-instance-plugin`, `cs-image-system-tf-s3-state-plugin` |
| Internal pin | `tf-ebs-instance-plugin` on `cs-image-system-aws-runtime-plugin==<the family's number>` |
| Entry points | runtime `aws_plugin`; bootstrap `aws`; modules; instance `tf-ebs-instance-plugin`; state `tf_s3_state_plugin` (unchanged) |
| Live tests | `validate --online` against the fixture's AWS account (read-only, nothing created), by `just test-live` and CI dispatch, with the AWS identity (`AWS_ROLE_ARN`) |
| An operator types | `uv tool install 'cs-image-system[aws]'` |
