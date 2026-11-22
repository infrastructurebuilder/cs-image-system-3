# Contract: the AWS family's repository

**Feature**: [spec.md](../spec.md) | **Decisions**:
[research.md](../research.md) R1, R3, R4, R9, R11 to R13

The AWS family's repository keeps the contract the Google Cloud family's
does, word for word but for the names:
[specs/005-relocate-gcp-provider/contracts/family-repository.md](../../005-relocate-gcp-provider/contracts/family-repository.md)
(its lifecycle targets, what a package declares, CI, what an operator
types). What differs:

| Item | The AWS family's |
| --- | --- |
| Repository | `infrastructurebuilder/cs-image-system-aws`, work on `develop`; public; GitHub's default branch is the operator's to set (`main` on 2026-11-21; the Google Cloud family's is `develop`) |
| Distributions | `cs-image-system-aws-runtime-plugin`, `cs-image-system-tf-ebs-instance-plugin`, `cs-image-system-tf-s3-state-plugin` |
| Internal pin | `tf-ebs-instance-plugin` on `cs-image-system-aws-runtime-plugin==<the family's number>` |
| Entry points | runtime `aws_plugin`; bootstrap `aws`; modules; instance `tf-ebs-instance-plugin`; state `tf_s3_state_plugin` (unchanged) |
| Live tests | `validate --online` against the fixture's AWS account (read-only, nothing created), by `just test-live` and CI dispatch, with the AWS identity (`AWS_ROLE_ARN`). On 2026-11-21 the repository holds no secret: the secret and the read-only role's trust of this repository are the operator's to set before the first dispatch |
| Test stubs | `cs_image_system.aws_runtime.testing` ships in `cs-image-system-aws-runtime-plugin` (phase 1 here); its own suite, the system's `tests/cloud_starters` and the Okta plugin's instance suite (spec 008) use it |
| Release | `just release <part-or-version> <index> [yes]` (the index `test` or `pypi`), copied from the Google Cloud family's fixed script (it commits only when the bump or the lock changed something and tags in every case); its releases go to PyPI, which the system's release probe asks |
| Known defect carried | `complete`'s dry run on `aws-east1` (spec 005's T078), named in its README, not fixed by the move |
| An operator types | `uv tool install 'cs-image-system[aws]'` |
