# Data Model: A provider that stands alone (docker first)

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) |
**Research**: [research.md](research.md)

This system stores nothing in a database. The "data" of this feature
is a small set of declarations and records, kept as files or as values
that live for one run. Each is described by what it holds, who owns
it, and the rules it must satisfy.

## The SDK

The three distributions a provider is written against: the kit
(`cs-image-system-base`), `cs-image-system-hashicorp-utils` and
`cs-image-system-tofu-roots`.

They are versioned on two lines, both separate from the workspace
version, both starting at 0.2.0 and staying below 1.0 until the
operator decides otherwise.

| Version line | Members | What a member depends on |
| --- | --- | --- |
| The kit | `cs-image-system-base` | The contract |
| The Terraform libraries | `cs-image-system-hashicorp-utils`, `cs-image-system-tofu-roots` | The contract. `tofu-roots` also depends on the kit by a range, and on `hashicorp-utils` exactly. |

Rules, for each line:

- Removing or altering a surface entry raises the middle number.
- Any other change to the bytes of a member raises the last number.
- A provider pins each member it uses by a range that covers one
  middle number.
- Every other workspace package pins the members exactly.

Rules for the Terraform libraries (FR-026):

- They use nothing of the kit that is not on the kit's surface.
- No module of the contract, the kit, the engine or the command line
  imports them.
- Their tests pass in an environment that holds only them and their
  declared dependencies.

## Surface declaration

One per SDK member, in the member's own `surface` module. It is the
one place that says what a plugin may use (FR-009).

| Field | Meaning |
| --- | --- |
| Library | The import package the declaration belongs to. |
| Names | For each public module, the names a plugin may import from it. |
| Hooks | For each class on the surface, the underscore-prefixed members a subclass may override or call. |

Rules:

- A name not listed is private, whatever its spelling.
- An underscore-prefixed member is usable by a plugin only if it is
  listed as a hook.
- The declaration ships inside the distribution, so a check can read
  the surface of whatever version is installed.

## Surface entry and baseline

A **surface entry** is one declared name or hook together with what a
plugin can observe of it:

| Kind | What is recorded |
| --- | --- |
| Function, method or hook | Its parameters, their kinds and defaults, and its return annotation. |
| Class | Its bases on the surface, and its public methods and declared hooks, each as above. |
| Model | The class record, plus each field's name, annotation, and whether it is required. |
| Constant | Its type and value. |

A **baseline** is the full list of an SDK member's surface entries as
they stood at the first release of the current middle number. One file
per member, committed, regenerated only by `just surface-record`.

State transitions of a baseline:

```text
recorded (middle number N)
   │  an entry is added          → still valid; last number rises
   │  an entry changes or goes   → INVALID until the middle number rises
   ▼
re-recorded (middle number N+1), in the same change that raises it
```

## Provider family

The distribution that serves one provider, with everything it needs.

| Field | For docker |
| --- | --- |
| Distribution | `cs-image-system-docker-plugin` |
| Directory | `packages/docker-plugin` |
| Import packages | `cs_image_system.docker_runtime`, `cs_image_system.tf_docker_plugin` |
| Namespaces | `docker-runtime`, `tf-docker` (unchanged, named in the plugin metadata) |
| Dependencies | The contract and the SDK members, each by range; third-party packages |
| Test dependencies | The core (a plain `cs-image-system`) and `pytest` |
| Terraform modules | `docker_container`, `docker_volume`, shipped in the distribution |
| Stubs | `cs_image_system.docker_runtime.testing` |
| Fixture | A docker-only configuration, in the family's `tests/fixture` |
| Golden | The fixture's pinned emission, in the family's `tests/golden` |

Rules:

- The source imports only the contract, declared SDK surface, and
  itself (FR-014, FR-019).
- The tests import only the above, the test kit and the family's own
  stubs (FR-002).
- Loading it and running it changes no process-wide state (FR-020),
  with the one exception recorded in research R16.

## The three suites

| Suite | Fixture | Golden | Environment that proves it |
| --- | --- | --- | --- |
| Core | `packages/system/tests/core_fixture` (test-double runtime, no provider, no Okta) | `packages/system/tests/core_golden` | A plain install, no extras |
| Docker family | the family's `tests/fixture` | the family's `tests/golden` | The family and its declared dependencies |
| Every-provider | [tests/fixtures/config](../../tests/fixtures/config), unchanged | [tests/fixtures/golden](../../tests/fixtures/golden), unchanged | Every provider installed |

Rule: a golden is compared byte for byte, and a new or moved golden is
read file by file (Constitution IV).

## Test kit

`cs_image_system.system.testing`: what a provider's tests use in place
of the workspace's shared harness. Its contract is in
[contracts/test-kit.md](contracts/test-kit.md).

| Part | Holds |
| --- | --- |
| The stubbed run | Copy a fixture; load a context; run the lifecycles with external commands recorded, not executed; a fixed clock; the tree that was emitted. Takes a list of provider stub functions. |
| Golden | Compare an emitted tree with a golden directory; regenerate one. |
| Test-double runtime | A runtime type that exists only inside a test run. Not an installed entry point. |
| Isolation assertion | Fails if a load and a run changed the environment, the working directory, `sys.path` or the root logger, or if the kit's opened-secret store lost an entry. |

## Isolated run report

What each isolated recipe prints and decides. One per run.

| Field | Meaning |
| --- | --- |
| Subject | `core`, `docker`, `docker (copy outside the workspace)`, `terraform libraries` or `docker install` |
| Installed | The distributions installed and where each SDK member came from: `index` or `this repository's build (development install)` |
| SDK end | For docker and for the Terraform libraries: `low` or `high`, with the version of each line |
| Collected / passed / skipped | Test counts |
| Verdict | Pass only if collected is above zero, skipped is zero and nothing failed |

## Unusable plugin record

What the loader keeps, per run, for each plugin it could not use.

| Field | Meaning |
| --- | --- |
| Plugin | Entry-point name and distribution |
| Cause | `failed to import`, `refused` (with the reason), or `collides` |
| Collides with | For a collision: the other plugin and the thing both claim |
| Words it would have registered | Used to tell a configuration that needs it why validation failed |

Rules:

- One line is logged per record (per pair, for a collision).
- A configuration that names none of its words is unaffected.
- A configuration that names one fails validation, and the message
  says the plugin is installed and gives the cause. It does not say
  "install the extra".

## Stand-in declaration

Not a new record: a runtime class whose `local_test_target()` returns
a factory has declared itself a stand-in.

| Installed stand-ins | Outcome of a check that needs one |
| --- | --- |
| Exactly one | Used; the run prints which |
| Two or more | Fails until the caller names one |
| None, or its daemon does not answer | Fails, unless the caller asked for the exclusion |
