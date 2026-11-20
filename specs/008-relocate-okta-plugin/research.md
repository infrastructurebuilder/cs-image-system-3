# Research: The Okta identity plugin in a repository of its own

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Marked **read** (seen on 2026-11-19), **decided** (the operator's, in the
spec's Clarifications) or **chosen** (this plan's, with alternatives).

## R1. What the Okta plugin is

**Read**: one distribution, `cs-image-system-okta-opa-plugin` 0.1.11
(`cs_image_system.okta_opa_plugin`), 4,152 source lines.

| Entry point group | Name | What |
| --- | --- | --- |
| `cs_image_system.plugins.group` | `okta_opa_plugin` | the group and user builders: `okta-tf` (managed groups), `okta-tf-ro` (lookups), the user builders |
| `cs_image_system.bootstrap` | `okta` | the setup section |
| `cs_image_system.commands` | `okta_opa_plugin` | the commands `workload` and `verify login` |
| `cs_image_system.modules` | `modules` | `tfmodules/okta_opa_module` |

It declares the `sftd-token` enrollment kind in its metadata (spec 004).
Its SDK pins are exact (`base==0.2.0`, `hashicorp-utils==0.2.0`,
`tofu-roots==0.2.0`); phase 1 makes them ranges. Its own tests: 71, four
of which use this repository's harness only for `bare_run` (the
Terraform library's, re-exported).

## R2. The order of work

**Chosen**: spec 005's four phases (prepare here and release; stand
alone there and release; remove here and release; the reference takes
it). This specification follows spec 005 and does **not** wait for spec
007: the AWS family's 0.1.11 is already on PyPI, released from this
repository, so the Okta plugin's repository can take it from the index
now, by a range that also admits the AWS family's own line
(`>=0.1.11,<0.3`). It must land before spec 007's phase 3 (spec 007,
research R7).

## R3. What carries the instance-side proofs there

**Decided** (Q1: A): the AWS family from the index, as a test
dependency of the Okta plugin's instance-side tests only, because the
configured Okta is reached from AWS today; replaceable later (the
operator's note), e.g. by the test kit's double runtime of spec 007
(research R6).

**Chosen, how**: the Okta plugin's repository keeps two suites:
- **its own** (`packages/okta-opa-plugin/tests`, where they are today,
  as the Google Cloud family kept its packages' tests): the group, user and lookup
  roots, the module objects, the workload policy and token, the gid shim,
  the server aliases, the app check -- needing the SDK and the test kit
  alone;
- **the instance suite** (`tests/instance`): enrollment at launch,
  activation in the bake, the login proof, the golden -- over a small
  fixture of its own (one AWS runtime, one image owned by an Okta group,
  one instance), with the AWS family from the index and the AWS stubs
  that family ships (spec 007's phase 1 moves them into
  `cs_image_system.aws_runtime.testing`; until that release, the suite
  carries its own copy, named as temporary).

The AWS dependency sits in a dependency group of that suite alone, so
replacing the vehicle touches nothing else.

## R4. What stays here, and the shared suite

**Chosen**:
- The core's identity seams stay proven here through the core's POSIX
  identity plugin (`cs-image-system-posix-identity-plugin`) and the test
  kit: the enrollment kinds a plugin declares (spec 004's tests), a group
  builder's launch parameters, a login proof a builder offers.
- The shared fixture's groups and users become POSIX (FR-006): the Okta
  group builders, `okta-groups-ro` and the users with Okta fields leave;
  every image keeps its group, now POSIX, with a gid and synthetic POSIX
  personas, as the Google Cloud family's fixture did.
- **Read**: the shared golden holds 14 identity files (`oktagroups` 8,
  `okta-tf-users` 3, `okta-groups-ro` 3) and the run script, and Okta
  lines in the bakes and the instance roots (enrollment, activation);
  all leave or change, read file by file.
- `tests/harness.py` loses its Okta parts (the dummy Okta credentials,
  `_identity_provider` and its retirement journal), which move to the
  plugin's own `cs_image_system.okta_opa_plugin.testing`.

## R5. CI

**Read**: this repository's `live` jobs gate on and pass the Okta triple
(`OKTA_API_PRIVATE_KEY`, `TF_VAR_NOS_KEY`, `TF_VAR_NOS_SECRET`), which the
Okta workspace asserts at load. Once the frozen fixture is POSIX, its
load no longer needs them; the starters' check (spec 005's research R11)
still renders `standard-aws` and `complete`, which declare Okta groups.

**Open, settled by a task (T003)**: whether loading those starters, and
`validate --online` on them, needs the real triple or only its presence.
If presence only, the triple leaves this repository's CI, as the spec's
edge case says, and the starters' check sets dummy values. If the real
triple, it stays for that check alone, and the spec's edge case is
corrected to say so. The workload login proof (`verify login`) is the
reference configuration's CI job and stays there.

## R6. The destination and versions

**Read**: `infrastructurebuilder/cs-image-system-okta` exists; GitHub's
default branch is `main`; a local `develop` is not on the remote yet.
**Chosen**: work on `develop` (pushed when the operator says), the
plugin's own line from 0.2.0; the system's `okta` and `all` extras name
it by `>=0.2,<0.3`.

## R7. Nothing live is touched

**Chosen** (Constitution III; the standing rule never to destroy OPA
groups or users): no task applies an identity root; the reference
configuration's drift check is the proof, and its plan must show no
change to any OPA group or user (spec SC-003).
