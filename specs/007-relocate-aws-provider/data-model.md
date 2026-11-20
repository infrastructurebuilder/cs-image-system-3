# Data model: The AWS provider family in a repository of its own

**Feature**: [spec.md](spec.md) | **Decisions**: [research.md](research.md)

No record of the system changes; distributions, suites and releases move.

## The AWS family

| Field | Value | Rule |
| --- | --- | --- |
| Distributions | `cs-image-system-aws-runtime-plugin`, `cs-image-system-tf-ebs-instance-plugin`, `cs-image-system-tf-s3-state-plugin` | Names, import packages, entry points unchanged |
| Version | one number for all three, its own line from 0.2.0 | Above every version the index holds (0.1.11) |
| SDK dependencies | contract, kit, Terraform libraries | Ranges only |
| Internal dependency | `tf-ebs-instance-plugin` on `aws-runtime-plugin` | Exact, at the family's number |
| Test dependencies | the test kit and the core plugins its fixture declares, from the index | Never another provider family; never the Okta plugin (it is spec 008's) |
| Home | `infrastructurebuilder/cs-image-system-aws`, `develop` | History carried |

## The shared suite (this repository)

| State | Providers | Golden |
| --- | --- | --- |
| After spec 005 | AWS, docker | 117 files |
| After phase 1 here | AWS, docker (two docker runtimes, two local backends); the core's tests on docker or the double | unchanged but for what the second docker runtime adds, read file by file |
| After phase 3 | docker and the test kit's double | about 59 files, every change read file by file |

## The test double (R6, decided (a))

| Part | Implements | Never |
| --- | --- | --- |
| A runtime type | network facts, an SSH proxy and a baked session agent, relabelling in place | an installed entry point: a test registers it, as the kit's double does today |
| A storage type | archive and restore, single attach, a non-POSIX store with a wipe, lifecycle rules, zones, relabelling, base-image prerequisites | the same |

## Releases

```text
phase 1   this repository releases     the AWS family still inside; ranges on the SDK; the test kit's double
phase 2   the AWS family releases 0.2.0 from its own repository
phase 3   this repository releases     without it; `aws` and `all` name it by >=0.2,<0.3
phase 4   the reference takes phase 3  drift check exits 0
```
