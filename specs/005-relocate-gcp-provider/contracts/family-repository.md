# Contract: the Google Cloud family's repository

**Feature**: [spec.md](../spec.md) | **Decisions**:
[research.md](../research.md) R5, R6, R8

What a plugin author, an operator and CI can rely on once the family
lives in `infrastructurebuilder/cs-image-system-google-cloud`. It
serves FR-001 to FR-005, FR-009 and FR-010.

## The lifecycle targets

| Target | Does |
| --- | --- |
| `just init` | `uv sync --locked --all-extras` from the index (no path source to another repository) |
| `just build` | Builds the three wheels |
| `just test` | Lint (ruff and REUSE), the type check (zero errors), the surface check of each package's sources, then every test (the packages' own, which also hold their tests to the surface; the pipeline suite and the golden; the release tool's) under the test kit's strict session: zero collected or any skip fails |
| `just full-test` | `just test`, then the low end of the SDK ranges: a fresh environment with everything at the oldest release the ranges allow, the packages' own tests and self-checks under the strict session. The starters that declare Google Cloud are not rendered here (research R11): the system's repository checks them where every provider is installed |
| `just release <part\|version> [test\|pypi] [yes]` | Probes first (clean checkout, no tag, no version the index ever listed for any of the three, the token), `yes` stops with the plan; then moves the family's one number in all three manifests, runs `full-test`, builds and publishes the three together, commits and tags; the pushes are the operator's |
| `just test-live` | What needs a Google Cloud session (`tests/live`), under the strict session; never part of `test` or `full-test` |

## What a package declares

```toml
dependencies = [
    "cs-image-system-contract>=0.5,<0.6",
    "cs-image-system-base>=0.2,<0.3",
    "cs-image-system-hashicorp-utils>=0.2,<0.3",
    # tf-gcp-plugin only:
    "cs-image-system-tofu-roots>=0.2,<0.3",
    "cs-image-system-gcloud-runtime-plugin==<the family's number>",
]
```

Entry points, unchanged:

| Group | Name | Value |
| --- | --- | --- |
| `cs_image_system.plugins.runtime` | `gcloud` | `cs_image_system.gcloud_runtime.main:initialize` |
| `cs_image_system.bootstrap` | `gcp` | `cs_image_system.gcloud_runtime.bootstrap:gcp_section` |
| `cs_image_system.modules` | `modules` | `cs_image_system.gcloud_runtime:tfmodules` |
| `cs_image_system.plugins.instance` | `tf-gcp-plugin` | `cs_image_system.tf_gcp_plugin.main:initialize` |
| `cs_image_system.plugins.state` | `gcs_state_plugin` | `cs_image_system.gcs_state_plugin.main:initialize` |

## CI

One workflow on every push (any branch, FR-003) and every pull request:
a fresh runner, OpenTofu, `just init`, `just test`, `just public-safe`.
The live tests run only by dispatch, with the operator's Google Cloud
identity (the secrets `GCP_WORKLOAD_IDENTITY_PROVIDER` and
`GCP_SERVICE_ACCOUNT`), and tear down what they stand up.

## What an operator types

Unchanged, and stated once, in the system's operations guide:

```sh
uv tool install 'cs-image-system[gcloud]'
```
