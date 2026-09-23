# The packages

The uv workspace is sixteen packages under `packages/`. Each has its own
README that describes it on its own terms: what it registers, its models
and how they extend the base models, its builder's hooks, what it emits,
and one example configuration. The core and the CLI are packages too.

The workspace root is the seventeenth, `cs-image-system`: no sources of its
own, a `==` pin on every package, so one install is the whole system
(`uv pip install cs-image-system==<version>`; see "Installing a release"
in [OPERATIONS.md](OPERATIONS.md)). Every package declares exactly the
third-party distributions its sources import and pins its siblings at its
own version; `tests/test_v2_package_metadata.py` holds it to that.

## The core

| Package | What it is |
| --- | --- |
| [base](../packages/base/README.md) | The core: the base models, the plugin contract and registry, the lifecycles and phases, the run context, meta-state, encryption, the public-safe gate, lineage, releases, retention, launch parameters. Every plugin depends on it. |
| [system](../packages/system/README.md) | The CLI host: the `cs-image-system` command and every subcommand. |
| [hashicorp-utils](../packages/hashicorp-utils/README.md) | A library, not a plugin: the terraform collector (providers, plugins, backends, sensitive values by reference), the terraform root mixin (init, the gated plan → gate → apply sequence), HCL rendering. Five plugins use it. |

## The plugins

Discovered through Python entry points (`cs_image_system.plugins.*`); each
registers model and builder classes under the classifications it claims.

| Package | Kind | `type:` keys it answers to |
| --- | --- | --- |
| [aws-runtime-plugin](../packages/aws-runtime-plugin/README.md) | runtime | `aws` |
| [gcloud-runtime-plugin](../packages/gcloud-runtime-plugin/README.md) | runtime | `gcloud` |
| [default-os-plugin](../packages/default-os-plugin/README.md) | OS families | the family names an OS builder declares |
| [packer-plugin](../packages/packer-plugin/README.md) | image builders | the packer builders for EBS and GCE images |
| [ansible-plugin](../packages/ansible-plugin/README.md) | modifications | `ansible` (playbooks) |
| [bash-mod-plugin](../packages/bash-mod-plugin/README.md) | modifications | `bash-remote` (script, scripts, ensure) |
| [okta-opa-plugin](../packages/okta-opa-plugin/README.md) | groups and users | the OPA group builder, the managed and read-only user builders |
| [tf-ebs-instance-plugin](../packages/tf-ebs-instance-plugin/README.md) | instances and storages | the terraform instance and storage builders |
| [tf-gcp-plugin](../packages/tf-gcp-plugin/README.md) | GCE terraform pieces | see its README for exactly what it registers |
| [tf-s3-state-plugin](../packages/tf-s3-state-plugin/README.md) | state backends | `s3` |
| [local-state-plugin](../packages/local-state-plugin/README.md) | state backends | `local` (a state file on disk; stage 47) |
| [gcs-state-plugin](../packages/gcs-state-plugin/README.md) | state backends | `gcs` (a Google Cloud Storage bucket; declared in the fixture, bound to nothing; stage 47) |
| [dummy-plugin](../packages/dummy-plugin/README.md) | extension template and test double | see its README |

The exact keys, aliases and classifications are in each README's "What it
registers" section, which is written from the package's `pyproject.toml`
and its `main.py`. The field-by-field reference for the YAML each plugin
reads is [CONFIGURATION.md](CONFIGURATION.md).

## The README contract

Every package README ends with the same four sections, in this order, so
a reader finds the same thing in the same place in every package; only a
`## Related` section may follow them. Stage 62 (2026-09-23) set the
contract; [tests/test_docs_contract.py](../tests/test_docs_contract.py)
holds every README to it and checks that every relative link in the
READMEs, in this file, in the root README, in
[WORKLOAD_CONNECTION.md](../WORKLOAD_CONNECTION.md) and in
[DAILY_DRIVER.md](../DAILY_DRIVER.md) resolves.

| Section | Answers |
| --- | --- |
| `## Prerequisites and integration` | what must exist outside the system before the plugin works (accounts, roles, APIs, tools, credentials, network), and how the plugin finds it -- which field or variable; "nothing" is an answer |
| `## Configuration reference` | every field the plugin reads, with type, default and meaning, in tables; fields accepted but not read, named as such; then the variations: what the plugin does differently by declaration (ephemeral or durable, pinned or follow, ensure or script, encrypted or clear, one runtime or another, dry or real) |
| `## What it tests and verifies` | what the plugin checks, when (at load, validate, generation, apply, after apply, in the state query), and where the verdict lands; "nothing" is an answer |
| `## When it fails` | the failures the plugin produces, what each means, where to look, what to do; failures that have actually happened first, with their dates |

The sections are written from the package's models, builders, tests and
`pyproject.toml` and from the two manuals, never from memory; where a
README and the code disagree, the code wins and the README is corrected.
Where the choice is between a little more explanation and a little less,
the README errs on the side of more.
