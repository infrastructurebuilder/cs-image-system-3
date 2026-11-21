# Feature Specification: The Google Cloud provider in a repository of its own

**Feature Directory**: `specs/005-relocate-gcp-provider`

**Feature Branch**: `feature/005-relocate-gcp-provider` (to be created from `develop` when planning starts)

**Created**: 2026-11-18

**Status**: Complete, 2026-11-20. Phase 1 merged into `develop` 2026-11-19 from `feature/005-prepare`; phases 2 to 4 merged 2026-11-20 from `feature/005-relocate-gcp-provider` (`0ba7077a`); the family released from `cs-image-system-google-cloud` at 0.2.0, this repository released without it at 0.1.12, the reference took it with its drift check green, and one live GCE cycle passed. Records are in [tasks.md](tasks.md).

## Clarifications

### Session 2026-11-18

- Q: Does this specification also make the Google Cloud family stand
  alone, or is that a prerequisite specification of its own? → A: One
  specification: the family is made to stand alone as it moves, its own
  tests, fixture and golden built once, in its new repository, with the
  machinery spec 001 made.
- Q: What happens to the shared "every provider installed" fixture and
  golden, and the tests here that exercise Google Cloud? → A: The Google
  Cloud parts move to the family's repository; the shared suite here
  keeps AWS and docker, and its golden is read file by file as it
  shrinks.
- Q: Does the system keep offering the family through its `gcloud` and
  `all` extras? → A: Yes, pinned by a range to the family's own
  releases, so `cs-image-system[gcloud]` installs as before.

**Input**: User description: "Relocate gcp provider to external repository"

**Users served**: a plugin author (primary: whoever owns the Google
Cloud family can build, test and release it without this repository);
operators (they install and run Google Cloud configurations exactly as
before); an adopting team (the Google Cloud starter still works).

## Why

Specification 001 proved that a provider family can stand alone, with
docker, and left the move of any family to a repository of its own to a
later specification. This is that move, for the Google Cloud family:
its runtime, its Terraform roots and its state backend
(`cs-image-system-gcloud-runtime-plugin`,
`cs-image-system-tf-gcp-plugin`, `cs-image-system-gcs-state-plugin`).
The destination exists, `cs-image-system-google-cloud`, with nothing in
it yet but a skeleton.

Google Cloud is the right second family because it is the one this
repository's owner pays for: a provider whose live cycle costs money
should be released and proven on its own schedule, and the core should
not need a Google Cloud identity, tool or test to change.

Today the family is not ready to leave. It pins the kit and the
Terraform libraries at exact versions, not ranges; its behaviour is
proven mostly by tests that live in this repository's shared suite
(about 27 of them import its code) and by the shared fixture and
golden, about a fifth of which is its emission; and it is released in
lockstep with everything else here.

This specification does both: the family is made to stand alone as it
moves. Its own tests, fixture and golden are built once, in its new
repository, with what spec 001 made (the isolated run, the test kit,
the SDK's declared surfaces and ranges), rather than first here and
then again there.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The family builds, tests and releases from its own repository (Priority: P1)

A plugin author clones `cs-image-system-google-cloud`, and with nothing
else checked out builds the three packages, runs their tests and cuts a
release. What the family needs of the system it takes from published
releases of the contract, the kit and the Terraform libraries, by the
ranges it declares.

**Why this priority**: this is the move. Without it the family has only
changed address.

**Independent Test**: in an empty environment, a fresh clone of the
family's repository runs its acceptance tests, against the newest and the
oldest SDK releases its ranges allow, and passes with nothing skipped.

**Acceptance Scenarios**:

1. **Given** a fresh clone of the family's repository and no checkout of
   this one, **When** its acceptance tests run, **Then** it builds the
   three packages, passes its own tests, fixture and golden, and skips
   nothing.
2. **Given** the oldest SDK releases the family's ranges allow, **When**
   the acceptance tests run against them, **Then** they pass, or names what that
   SDK lacks.
3. **Given** a release of the family, **When** it is installed beside a
   released system from the package index, **Then** a Google Cloud
   configuration validates and dry-runs.

---

### User Story 2 - This repository no longer holds the family (Priority: P2)

A maintainer of the core changes the kit, the engine or another
provider without a Google Cloud identity, the `gcloud` tool or the
family's code installed, and the acceptance tests here say nothing about Google
Cloud.

**Why this priority**: half the point of the move. Constitution VI:
one provider's presence must not change what another, or the core,
needs.

**Independent Test**: this repository's acceptance tests pass with no
Google Cloud package installed; no source, test, recipe or CI job here
imports, installs or runs the family's code.

**Acceptance Scenarios**:

1. **Given** this repository after the move, **When** its acceptance tests run,
   **Then** it passes with the family absent, the shared suite holds
   only its AWS and docker parts, and the workspace holds three
   packages fewer.
2. **Given** this repository's sources and tests, **When** they are
   searched for the family's packages, **Then** nothing imports them.
3. **Given** a change to the kit's surface, **When** it is released,
   **Then** the family learns of it from its own acceptance tests against the new
   release, not from this repository's.

---

### User Story 3 - An operator sees no difference (Priority: P3)

An operator with a Google Cloud configuration installs the system and
the family, and every command behaves and emits exactly as before the
move.

**Why this priority**: the move must be invisible to the people who
run the system. Constitution IV: the emission is the contract with the
past.

**Independent Test**: the reference configuration, with the family
installed from its own release, reports no change of its own emission
(`config-drift` exits 0), and the Google Cloud starter renders,
validates and dry-runs.

**Acceptance Scenarios**:

1. **Given** the reference configuration and the family installed from
   its own release, **When** the drift check runs, **Then** it exits 0,
   with no change that is the tree's own.
2. **Given** a configuration that writes a Google Cloud `type:` word
   bare or qualified, **When** it loads after the move, **Then** both
   forms load as before (the registrations keep their namespaces).
3. **Given** a configuration that names the Google Cloud runtime and a
   system without the family installed, **When** it is validated,
   **Then** it is told the runtime is not installed and how to install
   it.
4. **Given** the Google Cloud starter, **When** an adopting team
   renders it, **Then** it validates and dry-runs with the system and
   the family installed.

---

### User Story 4 - Each repository releases on its own (Priority: P4)

The system releases without the family, and the family releases
without the system, each proven against what it will be installed
with.

**Why this priority**: lockstep release is what ties the family to
this repository today; the move is only finished when that tie is
gone.

**Independent Test**: a release of the system succeeds with the family
untouched; a release of the family succeeds with the system untouched;
neither publishes a version that its own acceptance tests did not prove.

**Acceptance Scenarios**:

1. **Given** a system release, **When** it is cut, **Then** it neither
   builds nor publishes the family's packages, and its `gcloud` and
   `all` extras name the family by a range that a published family
   release satisfies.
2. **Given** a family release, **When** its acceptance tests did not pass against
   the SDK it claims, **Then** it is not published.
3. **Given** a system release that moves the contract's series,
   **When** the family's range does not include it, **Then** installing
   the two together is refused at install time, not at run time.

---

### Edge Cases

- A configuration that wrote a qualified word
  (`gcloud-runtime/gcloud`) loads unchanged: the distributions keep
  their names, so the namespaces derived from them stay.
- The family's Terraform modules, image-source catalog blocks and
  setup section ship inside its own packages and nothing of them stays
  here.
- The live leg of this repository's CI, which today dry-runs the frozen
  fixture with a Google Cloud identity, must not fail or silently
  succeed when the family is absent.
- The family's packages already exist on the package index under these
  names and versions; the move must not reuse a version the index
  holds, and a deleted version is never cut again.
- History: the family's files keep their commit history in the new
  repository.
- A Google Cloud live cycle costs the operator money; the move runs at
  most the cycles needed to prove it, and tears down whatever they
  stand up.

## Requirements *(mandatory)*

### Functional Requirements

**The family's repository**

- **FR-001**: The three packages, their tests, their fixture and
  golden, their Terraform modules and their documents MUST live in
  `cs-image-system-google-cloud`, under the same distribution names,
  import names and entry points as today.
- **FR-002**: The family MUST declare ranges, not exact versions, on
  the contract, the kit and the Terraform libraries, and its acceptance tests MUST
  pass at both ends of those ranges against published releases.
- **FR-003**: The family's repository MUST have the five lifecycle
  targets (`init`, `build`, `test`, `full-test`, `release`) and a CI
  job that runs its acceptance tests on every push.
- **FR-004**: The family's own tests MUST prove what this repository's
  shared tests prove of it today; a behaviour proven here before the
  move MUST be proven there, or its removal stated and justified.
- **FR-005**: The family's files MUST keep their commit history in the
  new repository.

**This repository**

- **FR-006**: The three packages MUST leave this workspace, with every
  test, recipe, CI step and document here that names them.
- **FR-007**: This repository's acceptance tests MUST pass with no Google Cloud
  package, tool or identity present, and skip nothing for the lack of
  one.
- **FR-008**: The Google Cloud parts of the shared fixture, golden and
  tests MUST move to the family's repository, where they become its
  own; the shared suite here MUST keep its AWS and docker parts and
  pass without the family. Every golden file that leaves or changes
  here MUST be read file by file, and the emission the family's
  repository holds MUST equal what this repository emitted for the same
  declarations before the move (Constitution IV).
- **FR-009**: The system's `gcloud` and `all` extras MUST keep
  installing the family, pinned by a range to the family's own
  releases, so `cs-image-system[gcloud]` installs as before. How an
  operator installs the family MUST be stated in one place and linked
  from the others.

**Releases**

- **FR-010**: The family MUST release from its own repository, on a
  version line of its own, and MUST NOT publish a version its acceptance tests did
  not pass.
- **FR-011**: The system's release MUST NOT build, test or publish the
  family.

**Behaviour**

- **FR-012**: With the family installed, every command MUST behave and
  emit as before the move: the reference configuration's drift check
  exits 0 with no change of its own, and the Google Cloud starter
  validates and dry-runs.
- **FR-013**: A configuration that names the family's words while the
  family is not installed MUST be told it is not installed, as for any
  absent plugin.
- **FR-014**: Every statement in this repository, the reference
  configuration and the starters that the move makes false MUST be
  corrected (Constitution X).

### Key Entities

- **The Google Cloud family**: the runtime, its Terraform roots and its
  state backend; three distributions that release together.
- **The family's repository**: `cs-image-system-google-cloud`, a
  workspace of the three packages with its own acceptance tests, CI and release.
- **The SDK**: the contract, the kit and the Terraform libraries,
  published from this repository, which the family ranges on.
- **The shared suite**: the fixture, golden and tests that install
  every provider of this repository together; after the move, AWS and
  docker.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A fresh clone of the family's repository passes its acceptance tests
  in an empty environment with zero tests skipped, at both ends of its
  SDK ranges.
- **SC-002**: This repository's acceptance tests pass with none of the three
  packages installed, and zero files here import them.
- **SC-003**: The reference configuration's drift check exits 0 with
  the family installed from its own release.
- **SC-004**: One release of the system and one of the family are each
  cut without touching the other repository.
- **SC-005**: This workspace holds three packages fewer, its source
  and test lines fall by at least the family's own, and the golden
  files that left it are all present, unchanged, in the family's
  repository.
- **SC-006**: Live Google Cloud cycles run for the move: at most the
  ones needed to prove it, with nothing they stood up left standing.

## Assumptions

- The destination is the existing repository
  `infrastructurebuilder/cs-image-system-google-cloud`; its uncommitted
  skeleton (a workspace manifest naming the three packages) is the
  operator's draft and a starting point, not a decision.
- Distribution names, import packages, entry points and namespaces do
  not change, so configurations and the package index see the same
  names.
- The family takes a version line of its own, starting above every
  version the index holds for these names.
- The family's history is carried with its files; the method is the
  plan's.
- The reference configuration (`cs-image-system-testconfig`) installs
  the family from its release, as it installs the system.
- The docker family stays in this repository; its move, and the AWS
  family's, are later specifications.
- Specification 004 (kinds in metadata) is merged first; the family
  ranges on the contract series it leaves (`>=0.5,<0.6`).
