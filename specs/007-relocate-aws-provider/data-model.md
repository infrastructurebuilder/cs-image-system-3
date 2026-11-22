# Data model: The AWS provider family in a repository of its own

**Feature**: [spec.md](spec.md) | **Decisions**: [research.md](research.md)

No record of the system changes; distributions, suites and releases move.

## The AWS family

| Field | Value | Rule |
| --- | --- | --- |
| Distributions | `cs-image-system-aws-runtime-plugin`, `cs-image-system-tf-ebs-instance-plugin`, `cs-image-system-tf-s3-state-plugin` | Names, import packages, entry points unchanged |
| Version | one number for all three, its own line from 0.2.0 | Above every version the index holds (0.1.12 on 2026-11-21); released to PyPI only |
| SDK dependencies | contract (`>=0.5,<0.6`), kit and Terraform libraries (`>=0.2,<0.3`) | Ranges only |
| Internal dependency | `tf-ebs-instance-plugin` on `aws-runtime-plugin` | Exact, at the family's number |
| Test dependencies | the test kit and the core plugins its fixture declares, from the index, in its workspace's dev group | Never another provider family; never the Okta plugin (it is spec 008's) |
| Test stubs | `cs_image_system.aws_runtime.testing`, shipped in the runtime package | Used by its own suite, by this repository's `tests/cloud_starters`, and by spec 008's instance suite |
| Home | `infrastructurebuilder/cs-image-system-aws`, `develop` | History carried; GitHub's default branch is the operator's (`main` on 2026-11-21) |

## The shared suite (this repository)

| State | Providers | Golden |
| --- | --- | --- |
| After spec 005 | AWS, docker | 117 files |
| After spec 008 | AWS, docker; every group POSIX | spec 008's figure: the Okta identity files leave, POSIX ones come |
| After phase 1 here | AWS, docker (two docker runtimes, two local backends); the core's tests on docker, the double's in the core suite | unchanged but for what the second docker runtime adds, read file by file |
| After phase 3 | docker alone (the double is never declared here: R6) | spec 008's figure less the 58 AWS files, every change read file by file |

## The test double (R6, decided (a))

| Part | Implements | Never |
| --- | --- | --- |
| A runtime type, cloud-shaped (`CloudBuilderBase`), beside today's container double (`test-double`), which is unchanged | network facts, an SSH proxy and a baked session agent, relabelling in place | an installed entry point: a test registers it, as the kit's double does today; a declaration in the shared fixture |
| A storage type | archive and restore, single attach, a non-POSIX store with a wipe, lifecycle rules, zones, relabelling, base-image prerequisites | the same |
| Its instances | the rows that need a launched subject | settled by phase 1's first task: the neutral root of `tofu-roots`, or a double instance builder |
| Where it is proven | the core's own suite and fixture (`packages/system/tests`), by `just test-core`, with no provider installed | the shared suite |

## Released elsewhere (this repository, after phase 3)

| Extra | Distributions | Range | Repository |
| --- | --- | --- | --- |
| `gcloud` | the Google Cloud family's three | `>=0.2,<0.3` | `infrastructurebuilder/cs-image-system-google-cloud` |
| `aws` | the AWS family's three | `>=0.2,<0.3` | `infrastructurebuilder/cs-image-system-aws` |

Each is named once, in `RELEASED_ELSEWHERE` of `scripts/with-released-families`, and left out of every sync of this repository's venv (research R12).

## Releases

```text
phase 0   spec 008 lands               the Okta plugin released elsewhere; the shared fixture's groups POSIX
phase 1   this repository releases     the AWS family still inside; ranges on the SDK; aws_runtime.testing; the test kit's double
phase 2   the AWS family releases 0.2.0 from its own repository
phase 3   this repository releases     without it; `aws` and `all` name it by >=0.2,<0.3; the probe finds 0.2.0 on PyPI
phase 4   the reference takes phase 3  drift check exits 0
```
