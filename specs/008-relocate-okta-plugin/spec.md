# Feature Specification: The Okta identity plugin in a repository of its own

**Feature Directory**: `specs/008-relocate-okta-plugin`

**Feature Branch**: `feature/008-relocate-okta-plugin` (to be created from `develop` when planning starts)

**Created**: 2026-11-19

**Status**: Draft

## Clarifications

### Session 2026-11-22

- Q: About 30 core tests prove hostname claims, provider aliases, the alias pool, canonical names and generations only through the Okta group builder's server registry; what carries them here once the plugin leaves? → A: The POSIX identity plugin gains a server registry and carries them (a feature specified on its own; this specification's T035 waits for it)

### Session 2026-11-19

- Q: What carries the Okta plugin's instance-side proofs in its own
  repository? → A: The AWS family from the index, as a test dependency,
  because the configured Okta is reached from AWS today. The operator's
  note: this holds only while Okta is installed on AWS; a later change
  may need another vehicle (for example the test kit's double runtime,
  spec 007's research R6), so the dependency is kept to the Okta
  plugin's instance-side tests and named as replaceable.

**Input**: User description: "Move the Okta identity plugin (cs-image-system-okta-opa-plugin: its OPA groups, users and lookups, its sftd-token enrollment kind, its login proof) out of this repository into infrastructurebuilder/cs-image-system-okta, so it builds, tests and releases on its own, by the pattern of spec 005 (the Google Cloud family) and spec 007 (the AWS family). Its instance-side behaviour (enrollment at launch, activation in the bake, the login proof), which today rides on a cloud runtime in this repository's shared suite, moves with it (spec 007's research R7, the operator's decision c). Serves a plugin author and operators."

**Users served**: a plugin author (primary: whoever owns the Okta
plugin builds, tests and releases it without this repository);
operators (their Okta groups, users and enrollment behave and emit as
before).

## Why

The Okta plugin (`cs-image-system-okta-opa-plugin`) manages OPA groups
and users, looks up existing ones, enrols launched instances with the
OPA server agent (`sftd-token`), activates a group's identity in the
bakes and proves a login. It is an identity plugin, not a provider, but
it is the last plugin whose behaviour this repository can only prove
through a cloud runtime: the core refuses an Okta-owned image on a
container runtime, so once the AWS family leaves (spec 007), nothing
here could carry the plugin's instance-side proofs. The operator
decided that the plugin moves out too, with those proofs (spec 007,
research R7, option c).

The destination exists: `infrastructurebuilder/cs-image-system-okta`
(one commit; GitHub's default branch `main`; a local `develop` not yet
on the remote).

In its own repository, the plugin's instance-side proofs run on the
AWS family, installed from the index as a test dependency, because the
configured Okta is reached from AWS today. That choice is tied to where
Okta is installed and may change: it is confined to those tests, so a
later vehicle replaces it without touching the rest.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The Okta plugin builds, tests and releases from its own repository (Priority: P1)

A plugin author clones the Okta plugin's repository and, with nothing
else checked out, builds it, runs its acceptance tests and cuts a
release, taking what it needs of the system from published releases by
the ranges it declares.

**Why this priority**: this is the move.

**Independent Test**: a fresh clone passes its acceptance tests in an
empty environment, at both ends of its SDK ranges, with nothing skipped.

**Acceptance Scenarios**:

1. **Given** a fresh clone and no checkout of this repository, **When**
   its acceptance tests run, **Then** the plugin's group, user and
   lookup roots, its enrollment kind and its login proof are all proven,
   and nothing is skipped.
2. **Given** a release of the plugin, **When** it is installed beside a
   released system and a cloud family, **Then** a configuration with
   Okta groups validates and dry-runs, and its instances' launch carries
   the enrollment step.

---

### User Story 2 - This repository no longer holds the Okta plugin (Priority: P2)

A maintainer of the core changes the kit or the engine without the Okta
plugin installed, and the acceptance tests here need no Okta
credentials, no OPA team and no Okta package.

**Why this priority**: the other half of the move (Constitution VI).

**Independent Test**: this repository's acceptance tests pass with the
Okta plugin absent; nothing here imports it.

**Acceptance Scenarios**:

1. **Given** this repository after the move, **When** its acceptance
   tests run, **Then** they pass with the plugin absent, and the
   workspace holds one package fewer.
2. **Given** the core's identity seams (enrollment kinds a plugin
   declares, a group builder's launch parameters, a login proof a
   builder offers), **When** the move is done, **Then** each is still
   proven here, through the core's POSIX identity plugin or a stand-in.

---

### User Story 3 - An operator sees no difference (Priority: P3)

An operator whose configuration uses Okta groups installs the system
with the plugin, and every command behaves and emits as before.

**Why this priority**: Constitution IV; the identity roots manage real
OPA groups and users, which must never be destroyed by a move.

**Independent Test**: the reference configuration, with the plugin
from its own release, reports no change of its own emission.

**Acceptance Scenarios**:

1. **Given** the reference configuration and the plugin from its own
   release, **When** the drift check runs, **Then** it exits 0.
2. **Given** a configuration that writes the plugin's words bare or
   qualified, **When** it loads, **Then** both forms load.

---

### Edge Cases

- The identity roots manage real OPA groups and users; the move must
  plan no destroy of any of them (Constitution III).
- The plugin's enrollment kind is declared in its metadata (spec 004);
  the system registers it for the accepted plugin, so nothing changes
  for the core's enrollment seam.
- The shared fixture's images are owned by Okta groups today (spec 007,
  research R7); once the plugin leaves, those groups' type is unknown
  here, so the shared fixture's groups become POSIX, as the Google
  Cloud family's fixture did (spec 005, research R7).
- The CI's workload login proof (`verify login`, the OPA role) is the
  plugin's; it moves with it, and this repository's CI stops asking for
  the Okta secrets.
- The plugin's name is on the package index with many releases; its
  first release from its own repository must not reuse a version.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The plugin, its tests, fixture and golden, its Terraform
  modules and its documents MUST live in
  `infrastructurebuilder/cs-image-system-okta`, under the same
  distribution name, import name and entry points, with their history.
- **FR-002**: The plugin MUST declare ranges on the contract, the kit
  and the Terraform libraries, and pass its acceptance tests at both ends
  of them against published releases.
- **FR-003**: Its repository MUST have the five lifecycle targets and a
  CI job that runs its acceptance tests on every push.
- **FR-004**: Its instance-side behaviour (enrollment at launch,
  activation in the bake, the login proof) MUST be proven in its own
  repository on the AWS family, installed from the index as a test
  dependency of those tests only; nothing else in the plugin, its
  packages' dependencies or its other tests may depend on the AWS family,
  so the vehicle can be replaced later (the operator's note: the choice
  holds while Okta is installed on AWS).
- **FR-005**: The plugin MUST leave this workspace with every test,
  recipe, CI step and document here that names it; this repository's
  acceptance tests MUST pass without it and skip nothing for its lack.
- **FR-006**: The shared fixture's groups and users MUST become POSIX;
  every golden file that changes MUST be read file by file.
- **FR-007**: The system's `okta` and `all` extras MUST keep installing
  the plugin, by a range on its own releases.
- **FR-008**: With the plugin installed, every command MUST behave and
  emit as before; the reference configuration's drift check exits 0.
- **FR-009**: Every statement the move makes false MUST be corrected.

### Key Entities

- **The Okta plugin**: one distribution, `cs-image-system-okta-opa-plugin`
  (`cs_image_system.okta_opa_plugin`): group, user and lookup builders,
  the `sftd-token` enrollment kind, the login proof.
- **Its repository**: `infrastructurebuilder/cs-image-system-okta`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A fresh clone of the plugin's repository passes its
  acceptance tests with zero tests skipped, at both ends of its SDK
  ranges.
- **SC-002**: This repository's acceptance tests pass with the plugin
  absent, and zero files here import it.
- **SC-003**: The reference configuration's drift check exits 0 with the
  plugin installed from its own release, and plans no change to any OPA
  group or user.

## Assumptions

- The AWS family is released from its own repository (spec 007, phase 2)
  before this plugin's repository depends on it from the index; until
  then those tests may take it from this repository's release 0.1.11 or
  later, which still carries it.
- Specs 005 and 007 set the pattern; this specification follows spec 005
  and runs before spec 007's phase 3, which removes the cloud runtime
  the plugin's proofs ride on here today (spec 007, research R7).
- The name, import package, entry points and namespace do not change.
- The plugin takes a version line of its own above every version the
  index holds.
- The POSIX identity plugin (`cs-image-system-posix-identity-plugin`) is
  the core's and stays here.
- No live Okta or OPA change is made by the move.
