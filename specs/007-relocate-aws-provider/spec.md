# Feature Specification: The AWS provider family in a repository of its own

**Feature Directory**: `specs/007-relocate-aws-provider`

**Feature Branch**: `feature/007-relocate-aws-provider` (to be created from `develop` when planning starts)

**Created**: 2026-11-19

**Status**: Draft

## Clarifications

### Session 2026-11-21

- Q: In what order do specs 002, 003, 006, 007 and 008 land? → A: 008 wholly first (six of the shared fixture's eight images are owned by Okta groups), then 003, then 007; 006 and 002 fit between, and 002, 003 and 006 are carried by one batched release
- Q: How does the AWS identity move? → A: As spec 005's did: set the secret and the role's trust for `cs-image-system-aws` before its first live dispatch; remove this repository's `AWS_ROLE_ARN` and its trust after phase 3's release reaches `main`
- Q: The new repository's default branch? → A: `develop`, as the Google Cloud family's
- Q: A live AWS cycle to prove the move? → A: None
- Q: Amend the three statements planning found false? → A: Yes, as the plan writes them

### Session 2026-11-19

- Q: Where does the AWS family go? → A: A new repository of its own,
  `infrastructurebuilder/cs-image-system-aws`, as the Google Cloud
  family's; the operator creates it.
- Q: What carries the core's behaviours once both cloud families are
  gone? → A: The docker family, the last provider in this repository: the
  tests that spec 005 re-hosted on AWS, and every other core test that
  runs through AWS, move onto the docker family's runtime and roots.

**Input**: User description: "Move the AWS provider family (the AWS-specific plugins: cs-image-system-aws-runtime-plugin, cs-image-system-tf-ebs-instance-plugin, cs-image-system-tf-s3-state-plugin) out of this repository so it builds, tests and releases on its own, as spec 005 does for the Google Cloud family. Serves a plugin author, operators and an adopting team."

**Users served**: a plugin author (primary: whoever owns the AWS family
builds, tests and releases it without this repository); operators (they
install and run AWS configurations exactly as before); an adopting team
(the AWS starters still work).

## Why

Specification 005 moves the Google Cloud family to a repository of its
own and proves the way: the family stands alone as it moves, on the SDK
and the test kit from the package index, with its own fixture, golden,
acceptance tests, CI and version line. The AWS family is the next: its
runtime (`cs-image-system-aws-runtime-plugin`), its OpenTofu roots for
instances and storage (`cs-image-system-tf-ebs-instance-plugin`) and its
S3 state backend (`cs-image-system-tf-s3-state-plugin`).

The AWS family is harder to move than the Google Cloud family, for three
reasons this specification must answer:

- **It is the shared suite's default.** The shared fixture's default
  runtime, image, instance and storage builders and state backends are
  AWS's, and spec 005 re-hosts on AWS the core behaviours that ran
  through GCE. Once AWS leaves too, the core's behaviours need a vehicle
  that stays here.
- **Other things lean on it.** The reference configuration keeps its GCE
  roots' state in S3; the CI runner image and the system's own CI carry
  AWS identities; the default starter is `standard-aws`.
- **No destination exists yet.** Google Cloud's repository existed before
  its move; AWS's does not. *(Since 2026-11-19 it exists:
  `infrastructurebuilder/cs-image-system-aws`, its default branch to become
  `develop`.)*

The AWS family goes to a new repository of its own,
`infrastructurebuilder/cs-image-system-aws`, which the operator creates,
in the same shape as the Google Cloud family's. The core's behaviours
that run through AWS here move onto the docker family, the last provider
in this repository.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The AWS family builds, tests and releases from its own repository (Priority: P1)

A plugin author clones the AWS family's repository and, with nothing else
checked out, builds the three packages, runs their acceptance tests and
cuts a release, taking what the family needs of the system from published
releases by the ranges it declares.

**Why this priority**: this is the move.

**Independent Test**: a fresh clone of the AWS family's repository passes
its acceptance tests in an empty environment, at both ends of its SDK
ranges, with nothing skipped.

**Acceptance Scenarios**:

1. **Given** a fresh clone and no checkout of this repository, **When** its
   acceptance tests run, **Then** the three packages build and pass their
   own tests, fixture and golden, and nothing is skipped.
2. **Given** a release of the AWS family, **When** it is installed beside a
   released system from the package index, **Then** an AWS configuration
   validates and dry-runs.

---

### User Story 2 - This repository no longer holds the AWS family (Priority: P2)

A maintainer of the core changes the kit, the engine or the docker family
without an AWS identity, the AWS command line or the AWS family's code
installed, and the acceptance tests here say nothing about AWS.

**Why this priority**: the other half of the move (Constitution VI).

**Independent Test**: this repository's acceptance tests pass with no AWS
package installed; nothing here imports the AWS family.

**Acceptance Scenarios**:

1. **Given** this repository after the move, **When** its acceptance tests
   run, **Then** they pass with the AWS family absent, and the workspace
   holds three packages fewer.
2. **Given** a core behaviour that the shared suite proved through AWS,
   **When** the move is done, **Then** that behaviour is still proven here,
   through a vehicle that stays here.

---

### User Story 3 - An operator sees no difference (Priority: P3)

An operator with an AWS configuration installs the system with the AWS
family, and every command behaves and emits as before.

**Why this priority**: the move must be invisible to the people who run
the system (Constitution IV).

**Independent Test**: the reference configuration, with the AWS family
installed from its own release, reports no change of its own emission, and
the AWS starters render, validate and dry-run.

**Acceptance Scenarios**:

1. **Given** the reference configuration and the AWS family from its own
   release, **When** the drift check runs, **Then** it exits 0, with no
   change that is the tree's own.
2. **Given** a configuration that writes an AWS `type:` word bare or
   qualified, **When** it loads after the move, **Then** both forms load.
3. **Given** the reference configuration's GCE roots, whose state is in
   S3, **When** both families are installed from their releases, **Then**
   they plan and emit as before.

---

### User Story 4 - Each repository releases on its own (Priority: P4)

The system, the Google Cloud family and the AWS family each release
without the others, each proven against what it will be installed with.

**Why this priority**: until the lockstep tie is gone, the move is not
finished.

**Independent Test**: a release of any one of the three repositories
neither builds nor publishes another's packages.

**Acceptance Scenarios**:

1. **Given** a system release, **When** it is cut, **Then** it publishes
   none of the AWS family's packages, and its `aws` and `all` extras name
   the family by a range a published release satisfies.
2. **Given** an AWS family release, **When** its acceptance tests did not
   pass against the SDK it claims, **Then** it is not published.

---

### Edge Cases

- A tree that keeps another family's state in S3 (the reference's GCE
  roots) needs the AWS family's state backend installed; installing the
  Google Cloud family alone must say so, not fail obscurely.
- The default starter is `standard-aws`: a system installed without the
  AWS family must still offer it, or say plainly which extra it needs.
- The live jobs here (`fixture-live`, and the starters' check of spec 005,
  which uses no cloud identity) must neither fail nor silently succeed
  once the AWS family's declarations leave this repository. *(Amended
  2026-11-21: the starters' check takes no AWS identity.)*
- The AWS family's names are on the package index with many releases;
  its first release from its own repository must not reuse a version the
  index holds.
- Its history is carried with its files.
- AWS live cycles cost money and are the operator's to run: the move
  runs none by default.

## Requirements *(mandatory)*

### Functional Requirements

**The AWS family's repository**

- **FR-001**: The three packages, their tests, fixture and golden, their
  Terraform modules and their documents MUST live in the AWS family's own
  repository, under the same distribution names, import names and entry
  points as today.
- **FR-002**: The AWS family MUST declare ranges, not exact versions, on
  the contract, the kit and the Terraform libraries, and its acceptance
  tests MUST pass at both ends of those ranges against published releases.
- **FR-003**: The AWS family's repository MUST have the five lifecycle
  targets and a CI job that runs its acceptance tests on every push.
- **FR-004**: The AWS family's own tests MUST prove what this repository's
  tests prove of it today, or the removal of each proof MUST be stated and
  justified.
- **FR-005**: The AWS family's files MUST keep their commit history.

**This repository**

- **FR-006**: The three packages MUST leave this workspace, with every
  test, recipe, CI step and document here that names them.
- **FR-007**: This repository's acceptance tests MUST pass with no AWS
  package, tool or identity present, and skip nothing for the lack of one.
- **FR-008**: Every core behaviour the shared suite proves through AWS
  MUST stay proven here, through the docker family's runtime and roots;
  a behaviour docker cannot show (a capability only a cloud runtime has)
  MUST be named, and either proven here by the test kit's double runtime
  (research R6 (a)), carried to the AWS family's repository, or stated as
  no longer proven here, with the reason. *(Amended 2026-11-21.)*
- **FR-009**: The shared fixture's AWS parts and every golden file that
  leaves or changes MUST be read file by file (Constitution IV).
- **FR-010**: The system's `aws` and `all` extras MUST keep installing the
  AWS family, by a range on its own releases.

**Releases and behaviour**

- **FR-011**: The AWS family MUST release from its own repository, on a
  version line of its own, and MUST NOT publish a version its acceptance
  tests did not pass.
- **FR-012**: With the AWS family installed, every command MUST behave and
  emit as before; the reference configuration's drift check exits 0.
- **FR-013**: Every statement in this repository, the reference
  configuration and the starters that the move makes false MUST be
  corrected (Constitution X).

### Key Entities

- **The AWS family**: the AWS runtime, its OpenTofu roots, its S3 state
  backend; three distributions released together.
- **The AWS family's repository**: its home, with its own acceptance
  tests, CI and release.
- **The shared suite**: this repository's fixture, golden and tests that
  install every provider here; after spec 005, AWS and docker; after this
  specification, docker alone.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A fresh clone of the AWS family's repository passes its
  acceptance tests in an empty environment with zero tests skipped, at
  both ends of its SDK ranges.
- **SC-002**: This repository's acceptance tests pass with none of the
  three packages installed, and zero files here import them.
- **SC-003**: The reference configuration's drift check exits 0 with both
  cloud families installed from their own releases.
- **SC-004**: One release each of the system, the Google Cloud family and
  the AWS family is cut without touching the other two repositories.
- **SC-005**: Every core behaviour the shared suite proved through AWS
  before the move has a passing test here after it.

## Assumptions

- Spec 005 is finished first: its pattern (the SDK and test kit from the
  index, a strict session, a family harness, a fixture and golden of the
  family's own, read file by file against the shared golden) is reused
  whole, and its open defect (spec 006) is independent of this one.
- Distribution names, import packages, entry points and namespaces do not
  change, so configurations and the package index see the same names.
- The AWS family takes a version line of its own, starting above every
  version the index holds.
- The AWS family's fixture uses the core's POSIX identity, as the Google
  Cloud family's does, so its tests need no identity plugin.
- The reference configuration keeps its GCE roots' state in S3; it
  installs both cloud families by its one pin, as today.
- No AWS live cycle runs for the move unless the operator decides one.
