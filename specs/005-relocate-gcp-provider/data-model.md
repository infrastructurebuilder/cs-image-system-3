# Data model: The Google Cloud provider in a repository of its own

**Feature**: [spec.md](spec.md) | **Decisions**: [research.md](research.md)

No record or field of the system changes. What this feature moves are
distributions, test suites and the releases that tie them together.

## The Google Cloud family

| Field | Value | Rule |
| --- | --- | --- |
| Distributions | `cs-image-system-gcloud-runtime-plugin`, `cs-image-system-tf-gcp-plugin`, `cs-image-system-gcs-state-plugin` | Names, import packages and entry points unchanged (FR-001) |
| Version | one number for all three, on the family's own line from 0.2.0 | Above every version the index holds; never one the index ever held (R8) |
| SDK dependencies | contract, kit, Terraform libraries | Ranges only (FR-002): `>=0.5,<0.6`, `>=0.2,<0.3`, `>=0.2,<0.3` |
| Internal dependency | `tf-gcp-plugin` on `gcloud-runtime-plugin` | Exact, at the family's own number |
| Test dependencies | `cs-image-system-system[testing]` and the core plugins its fixture declares | Ranges, from the index |
| Home | `infrastructurebuilder/cs-image-system-google-cloud`, branch `develop` | History carried (FR-005) |

## The family's suite

| Part | Holds | Compared with |
| --- | --- | --- |
| Unit tests (per package) | The tests the packages carry today, and the surface self-check | — |
| Pipeline tests (`tests/pipeline`) | The Google-Cloud-only tests moved from here, and the family's part of the mixed tests | — |
| Fixture (`tests/fixture`) | The Google Cloud declarations of today's shared fixture, its roots bound to the family's own `gcs` backend | The shared fixture before the move |
| Golden (`tests/golden`) | The family's emission for its fixture | The shared golden before the move, file by file; every difference a consequence of the backend (R7) |
| Live tests (`tests/live`) | Tests that need a Google Cloud session | Never in `just test`; the operator's decision to run |

## The shared suite (this repository)

| State | Fixture | Golden |
| --- | --- | --- |
| Before | AWS, Google Cloud, docker | 148 files |
| After | AWS, docker | 117 files, and the GCE lines gone from 6 shared files; every change read file by file (R10) |

## Releases

```text
phase 1   this repository releases     SDK at contract 0.5.0, kit 0.2.0, Terraform 0.2.0, test kit with `strict`;
                                       the family still inside, on the workspace's number
phase 2   the family releases 0.2.0    from its own repository, against phase 1's SDK
phase 3   this repository releases     without the family; `gcloud` and `all` name it by >=0.2,<0.3
phase 4   the reference takes phase 3  drift check exits 0
```

A release of either repository afterwards needs nothing of the other's
except what its ranges name on the index.
