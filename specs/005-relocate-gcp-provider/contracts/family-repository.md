# Contract: the Google Cloud family's repository

**Feature**: [spec.md](../spec.md) | **Decisions**:
[research.md](../research.md) R5, R6, R8

What a plugin author, an operator and CI can rely on once the family
lives in `infrastructurebuilder/cs-image-system-google-cloud`. It
serves FR-001 to FR-005, FR-009 and FR-010.

## The lifecycle targets

| Target | Does |
| --- | --- |
| `just init` | `uv sync --locked` from the index (no path source to another repository) |
| `just build` | Builds the three wheels |
| `just test` | Lint, the type check (zero errors), the surface self-check of each package, the unit and pipeline tests and the golden, under the test kit's strict session: zero collected or any skip fails |
| `just full-test` | `just test`, then the same at the low end of the SDK ranges (unit tests and the self-check, as docker's low end), then `standard-gce` and `complete` rendered, validated and dry-run with the system from the index |
| `just release <part> [test\|pypi]` | Moves the family's one number in all three manifests, runs `full-test`, builds and publishes the three together; refuses a version the index ever held |

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

One workflow on every push to `develop` and every pull request: a fresh
runner, `just init`, `just test`. The live tests run only by dispatch,
with the operator's Google Cloud identity, and tear down what they
stand up.

## What an operator types

Unchanged, and stated once, in the system's operations guide:

```sh
uv tool install 'cs-image-system[gcloud]'
```
