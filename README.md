# cs-image-system

[![CI](https://github.com/infrastructurebuilder/cs-image-system-3/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/infrastructurebuilder/cs-image-system-3/actions/workflows/ci.yml)

A plugin-based, configuration-driven system that turns one YAML tree into
infrastructure-as-code for identities, storages, base images and instance
images, and applies it through gates, on AWS and GCE. Its purpose is
scientific compute: machine images that are correct for a given HPC model,
formally released, whose users log in through Okta Privileged Access.

## Where to start

- [DAILY_DRIVER.md](DAILY_DRIVER.md) — how a person actually uses the system: what must exist first, the first run, making and changing things, what proves what, and what a failure means.
- [DESCRIPTION.md](DESCRIPTION.md) — what the system is and how it works, in one read.
- [GOALS.md](GOALS.md) — what it is for and the properties it keeps.
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — the operating manual: runs, the developer workflow, CI, the operator's cycles, the rules.
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — the configuration reference: every file, every type, every field, one example each.
- [docs/DESIGN.md](docs/DESIGN.md) — the design and its rationale.
- [docs/PLUGINS.md](docs/PLUGINS.md) — the packages, each with its own README ending in the same four sections: prerequisites, configuration, what it tests, when it fails.
- [GOLDEN.md](GOLDEN.md) — the pinned emission every change is judged against.
- [PARITY.md](PARITY.md) — how the system and its documentation can diverge, and how to check.
- [BILLING_REMINDERS.md](BILLING_REMINDERS.md) — the GCP account's cost housekeeping.
- [docs/history/](docs/history/README.md) — frozen records of how the system got here; nothing there describes the present.
- [TODO.md](TODO.md) and [PLAN.md](PLAN.md) — the work in flight; a worksheet, not documentation.

## The Justfile contract

The `Justfile` is the single entry point for the build lifecycle. Five
names are reserved, in lifecycle order:

| Target      | Does                                                                                   |
|-------------|----------------------------------------------------------------------------------------|
| `init`      | Toolchain and every workspace package (`uv sync`), the pre-commit hook; idempotent     |
| `build`     | Every workspace member as sdist + wheel under `dist/`; no tests                        |
| `test`      | The fast suite, all blocking: ruff, pyright, the unit tests (the golden included)      |
| `full-test` | `test` plus the docker-backed modification tests and, when the runtime sessions are present, a headless dry `run --all` with `state query --strict`; an absent prerequisite reports SKIPPED |
| `release`   | `just release <part\|version> [test\|pypi]`: probe the index and the token, then the bar (TestPyPI) or `full-test` (PyPI), bump every version line and pin, lock, `build`, publish, commit, tag `v<version>` |

`just` alone lists every recipe, the contract first. `just publish
[test|pypi]` builds and uploads the version in the tree (TestPyPI by
default; a pushed `v*` tag makes CI do the same). `just cli …` runs
the CLI against the live configuration; the `cloud-*` and `gce-*` recipes
are the sanctioned cloud change cycle; `just public-safe` is the gate that
keeps secrets and people out of anything published. The manual describes
each.

## Layout

`packages/` holds the uv workspace: `base` (models, lifecycles, state),
`system` (the CLI), `hashicorp-utils` (the terraform library) and one
package per plugin (AWS and GCE runtimes, packer, ansible and bash
modifications, Okta identity, terraform storage and instance builders, the
GCP terraform pieces, the S3 state backend). `tfmodules/` are the terraform
modules the builders emit calls to. `tests/` is the suite, with the frozen
fixture configuration under `tests/fixtures/config/` and the golden
emission under `tests/fixtures/v2_golden/`. The live configuration is its
own repository, `cs-image-system-testconfig`, checked out beside this one
(`CSIS_CONFIG_ROOT` overrides); the tests never read it.

## Licence

Apache-2.0 ([LICENSE](LICENSE)); every package carries the licence file and
declares it in its project metadata.
