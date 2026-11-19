# Data model: The Okta identity plugin in a repository of its own

**Feature**: [spec.md](spec.md) | **Decisions**: [research.md](research.md)

## The Okta plugin

| Field | Value | Rule |
| --- | --- | --- |
| Distribution | `cs-image-system-okta-opa-plugin` | Name, import package, entry points unchanged |
| Version | its own line from 0.2.0 | Above 0.1.11, the index's newest |
| SDK dependencies | contract, kit, Terraform libraries | Ranges only |
| Test dependencies | the test kit and the core plugins its fixtures declare; the AWS family (`>=0.1.11,<0.3`) in the instance suite's group alone | Replaceable (the operator's note) |
| Home | `infrastructurebuilder/cs-image-system-okta`, `develop` | History carried |

## Its suites

| Suite | Needs | Proves |
| --- | --- | --- |
| `packages/okta-opa-plugin/tests` | the SDK, the test kit | group, user and lookup roots; module objects; workload policy and token; gid shim; server aliases; app check; the setup section; the commands |
| `tests/instance` | the above and the AWS family | enrollment at launch, activation in the bake, the login proof, the golden of its fixture |

## The shared suite here

| State | Identity | Golden |
| --- | --- | --- |
| Before | Okta groups and users (and one POSIX group) | the identity roots' 14 files and the Okta lines of the bakes and instance roots |
| After | POSIX groups and users only | identity files gone; bakes and roots with POSIX activation; every change read file by file |
