# Feature Specification: Releases go to TestPyPI until 1.0

**Feature Directory**: `specs/013-testpypi-until-1-0`

**Feature Branch**: `feature/013-testpypi-until-1-0` (to be created when planning starts)

**Created**: 2026-11-23

**Status**: In progress, 2026-11-24: its scope trimmed to the minimum (Clarifications, 2026-11-24), and phases 1 to 9 implemented on `feature/013-testpypi-until-1-0` (not merged), with the Okta plugin's and the Google Cloud family's changes on a branch of the same name in each (not pushed). T033 (the first TestPyPI-only release, with `--full`) and T034 (the reference configuration's take and `config-drift`) are the operator's. Records are in [tasks.md](tasks.md).

**Input**: User description: "Releases go to TestPyPI until 1.0. The operator's standing decision of 2026-11-23: until the operator declares 1.0, every release of cs-image-system-3 (the system, the contract, the kit and the Terraform libraries, every plugin it releases), of the Okta plugin (cs-image-system-okta) and of the Google Cloud family (cs-image-system-google-cloud) is published to TestPyPI only; PyPI keeps its last versions (system 0.1.12, SDK 0.2.1, contract 0.5.0, both families 0.2.1). Versions move only their third number meanwhile (a separate standing rule). Today much of the tooling assumes PyPI: uv and pip resolve from PyPI by default, so this repository's lock takes the families from PyPI through the okta, gcloud and all extras; the families' own locks and CI take the system, the SDK and the test kit from PyPI and so test against the old system; the reference configuration's `just take` and an adopting team's `uv tool install 'cs-image-system[okta]'` install PyPI's versions; the families' Publish workflows upload a final version to PyPI after TestPyPI; scripts/isolated-run resolves the SDK's low and high ends from PyPI and compares built wheels with PyPI's files; the released-elsewhere probe and `with-released-families --check` ask PyPI only; this repository's `just release <v> test` runs only the install check, not full-test nor the session probes, so a TestPyPI release is less proven than a PyPI one was; the starter template repositories are pushed only for a final PyPI release; the documentation's install lines install PyPI's versions. Every consumer must take the cs-image-system packages from TestPyPI, and only those (every other dependency from PyPI: TestPyPI as a general index invites a squatted name), each release must be proven as fully as a PyPI release was, nothing may publish to PyPI until 1.0, and every document that says how to install must say how to install a TestPyPI release. TestPyPI's own limits (it has been wiped before, its rate limits and outages) are accepted risks the documents name. Serves operators (who release and take releases), an adopting team (who installs one), and a plugin author (whose plugin is tested against the system it will run beside)."

**Users served**: operators (who cut releases and take them into the
reference configuration); an adopting team (who installs the system to run
their own tree); a plugin author (whose plugin, released from its own
repository, must be tested against the system it will run beside).

## Why

The system is published to two package indexes: PyPI, the public one that
every install reads by default, and TestPyPI, its practice twin. By the
operator's standing decision of 2026-11-23, every release from now until
the operator declares 1.0 goes to TestPyPI only. The reason, in the
operator's words: not to "flood actual pypi with interim releases", of
which there will be "quite a number". PyPI keeps the versions it
has: the system 0.1.12, the SDK 0.2.1, the contract 0.5.0, and both
families released elsewhere at 0.2.1.

The tools assume PyPI almost everywhere. An install reads PyPI unless told
otherwise, so after the next release:

- an adopting team following the install instructions would get the old
  system;
- the reference configuration's take of a release would install the old
  system;
- this repository's own lock, and the families' locks and CI, would keep
  testing against the old versions of each other, never the ones about to
  run together;
- the checks a release runs first, and the test that installs the SDK's
  oldest and newest versions, would read the wrong index;
- the families' publishing would also upload every final version to PyPI;
- the starter template repositories, pushed only for a final PyPI release,
  would never move.

And a release to TestPyPI is today proven less than a PyPI release was: it
runs an install check, not the full test suite or the checks of the
reference configuration's sessions.

TestPyPI is a test service: anyone may upload under any free name there,
and it has been wiped before. So the system's own packages are taken from
it, and nothing else is.

## Clarifications

### Session 2026-11-23

- Q: Where do releases go until 1.0? → A: TestPyPI only, for every
  repository (the operator's standing decision); versions move only their
  third number meanwhile (a second standing decision)
- Q (the operator's note): why TestPyPI? → A: To keep PyPI free of the
  many interim releases to come before 1.0; releases will be frequent
- Q: Is every interim release proven in full? → A: No. An interim
  release runs a lighter check; the full proof (the full test suite and
  the reference configuration's session checks) runs when the operator
  asks for it, and the operator is told, before a release, when a full
  proof is probably needed (what the release carries touches what only
  the full proof exercises)
- Q: How does this repository publish to TestPyPI? → A: By trusted
  publishing, as the two families do: a pushed tag runs a publishing
  workflow, with no upload token anywhere; the stored `TEST_PYPI_TOKEN`
  and `PYPI_TOKEN` secrets are no longer needed

### Session 2026-11-23 (planning)

- Q (D1): how does an install take the families' newest TestPyPI
  releases? → A: each system release pins every family extra exactly at
  the newest TestPyPI release inside its range
- Q (D2): how do the families test against the newest system? → A: a CI
  job that re-locks the system's names to TestPyPI's newest and runs the
  acceptance tests, beside the committed lock's job
- Q (D3): the Okta plugin's copy here? → A: marked `Private :: Do Not
  Upload` now

### Session 2026-11-24 (the scope trimmed)

- Q (the operator): "All I want is to pause real releases to pypi and
  ignore semantic versioning rules until we get closer to a 'real'
  release. This spec suddenly feels excessive." → A: **trimmed to the
  minimum**. Kept: PyPI refused in all three repositories (FR-001); the
  lighter check, the advisory and `--full` (FR-002, FR-002a); the
  release's probes reading TestPyPI (FR-005); trusted publishing, already
  built (FR-009); the lifting at 1.0, said once (FR-008). FR-003 is
  narrowed to the consumers that must read TestPyPI for a release to be
  usable at all: the reference configuration's take, the starters' CI and
  each repository's lock. Dropped: FR-004 (the families' job against the
  newest release and their oldest-versions leg through TestPyPI), FR-006
  (the starters stay pushed for final releases only, as before), FR-007
  (one statement in the operations guide, not every install line), and
  their success criteria SC-004 and SC-005. The patch-only versions rule
  needs no code: it is a standing rule a bump follows

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A release is published to TestPyPI only, proven enough for what it carries (Priority: P1)

An operator cuts a release of the system, the Okta plugin or the Google
Cloud family. An interim release runs a lighter check; the release says,
before it runs, when what it carries probably needs the full proof, and
the operator can ask for that proof on any release. It is published to
TestPyPI, and nothing reaches PyPI.

**Why this priority**: every other story takes releases; a release that
reaches PyPI breaks the decision, and interim releases must stay cheap
(there will be many) without hiding when one needs more.

**Independent Test**: a rehearsed interim release of each repository runs
the lighter check and publishes to TestPyPI; a rehearsed release carrying
a change the full proof exercises says so before it runs; a release asked
for the full proof runs it; a check of PyPI afterwards finds its newest
version unchanged.

**Acceptance Scenarios**:

1. **Given** an interim release of this repository, **When** it runs,
   **Then** it runs the lighter check (the acceptance tests, the install
   check, the version and surface probes), and stops before anything
   changes when one fails.
2. **Given** a release whose changes since the last fully proven release
   touch what only the full proof exercises, **When** it starts, **Then**
   it says the full proof is probably needed, naming why, before anything
   changes.
3. **Given** a release the operator asks to prove in full, **When** it
   runs, **Then** it runs every check the PyPI form ran (the full test
   suite, the reference configuration's session checks) and records that
   it was fully proven.
4. **Given** a release of the Okta plugin or the Google Cloud family,
   **When** its tag is pushed, **Then** its publishing uploads to TestPyPI
   and never to PyPI, whatever the version.
5. **Given** any release in any of the three repositories, **When** it is
   asked to publish to PyPI, **Then** it refuses, naming the standing
   decision, until the operator lifts it.
6. **Given** a release, **When** it finishes, **Then** PyPI's newest
   version of every package it carries is unchanged.

---

### User Story 2 - Every consumer takes the system's packages from TestPyPI, and only those (Priority: P1)

The reference configuration, an adopting team's install, this
repository's lock and the families' locks and CI take every
`cs-image-system` package from TestPyPI, and every other dependency from
PyPI.

**Why this priority**: a release nobody installs proves nothing, and a
consumer that took a third-party package from TestPyPI could take a
squatted one.

**Independent Test**: after a TestPyPI release, the reference
configuration's take installs it; a clean machine following the install
instructions installs it; each repository's lock names it; and in every
one of them no package other than the system's own comes from TestPyPI.

**Acceptance Scenarios**:

1. **Given** a release on TestPyPI, **When** the reference configuration
   takes it, **Then** the take installs that version and its drift check
   is green.
2. **Given** a clean machine, **When** an adopting team follows the
   install instructions, **Then** it installs the newest TestPyPI release,
   with the extras it names.
3. **Given** this repository and each family, **When** its lock is made,
   **Then** each other repository's packages come from TestPyPI at their
   newest release there, and every other dependency from PyPI.
4. **Given** any of these installs, **When** a package not of the system
   has a version on TestPyPI, **Then** it is still taken from PyPI.

---

### User Story 3 - A plugin is tested against the system it will run beside (Priority: P2)

A plugin author's repository (the Okta plugin, the Google Cloud family)
runs its tests, at both ends of its ranges, against the system's newest
TestPyPI release, so a change in the system that breaks it is found
there, before it is installed beside it.

**Why this priority**: the families are released apart from the system,
and this is the only place their compatibility is proven.

**Independent Test**: a family's acceptance tests and its oldest-versions
leg install the system's packages from TestPyPI, at the newest and the
oldest release their ranges allow there.

**Acceptance Scenarios**:

1. **Given** a family's acceptance tests, **When** they run, **Then** the
   system, its SDK and its test kit come from TestPyPI's newest release
   inside the family's ranges.
2. **Given** the family's oldest-versions leg, **When** it runs, **Then**
   it installs the oldest release its ranges allow, from either index.
3. **Given** this repository's test that installs the SDK alone at both
   ends, **When** it runs, **Then** it reads TestPyPI for the SDK's
   published versions and compares built files with TestPyPI's.

---

### User Story 4 - The documents say how to install a TestPyPI release, and what it risks (Priority: P2)

Every document that says how to install the system, a plugin or a starter
says how to install a TestPyPI release, and names TestPyPI's limits.

**Why this priority**: a team following an old install line gets the old
system without knowing it.

**Independent Test**: every install line in the three repositories'
documents and the starters, run on a clean machine, installs the newest
TestPyPI release; each such document names TestPyPI's limits once, by a
link to one statement.

**Acceptance Scenarios**:

1. **Given** the operations guide's install section, **When** it is
   followed, **Then** it installs the newest TestPyPI release with its
   extras.
2. **Given** each family's README and the starters' instructions, **When**
   followed, **Then** each installs from TestPyPI the same way.
3. **Given** these documents, **When** read, **Then** each links one
   statement of TestPyPI's limits (it may be wiped, it has rate limits and
   outages) and what the system does about them.

---

### User Story 5 - The starter repositories follow the releases (Priority: P3)

The starter template repositories are pushed for each release, as they
were for a final PyPI release.

**Why this priority**: they are an adopting team's first step; they
should not freeze at the last PyPI release.

**Independent Test**: after a release, each starter repository names that
release.

**Acceptance Scenarios**:

1. **Given** a release on TestPyPI, **When** its publishing finishes,
   **Then** each starter repository is pushed with that release named.

### Edge Cases

- TestPyPI is unreachable during a release: the release stops before
  anything changes, as it does for any index it cannot ask.
- TestPyPI has lost a version (a wipe): a take or an install of it fails
  naming the version; the version is never re-cut (an index that held a
  version never takes it again); the next patch is cut instead.
- A version exists on PyPI but not TestPyPI (the last PyPI versions):
  installs that ask for a range including it may take it from PyPI.
- A third-party package squats a name on TestPyPI: no consumer takes it.
- The operator lifts the decision at 1.0: the switch back is one change
  per repository, named in the documents.
- A development version (`.dev`): TestPyPI, as before.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Until the operator lifts the decision, no release of any of
  the three repositories MUST publish to PyPI; a release asked to MUST
  refuse, naming the decision.
- **FR-002**: An interim release MUST run a lighter check (the acceptance
  tests, the install check, the version and surface probes); a release
  the operator asks to prove in full MUST run every check the PyPI form
  of that repository's release ran, and MUST record that it was. *(The
  operator, 2026-11-23: "I want the lighter check".)*
- **FR-002a**: Before a release runs, it MUST say when a full proof is
  probably needed: when what it carries since the last fully proven
  release touches what only the full proof exercises (a runtime's or an
  identity's calls to its cloud or service, the release and take tooling,
  the starters' workflows, the contract or the SDK), or when the reference
  configuration is about to take it into an applying cycle, naming the
  reason; it MUST NOT refuse on that ground alone.
- **FR-003** *(narrowed 2026-11-24)*: The consumers a release must reach
  to be usable (the reference configuration's take, the starters' CI, and
  each repository's lock) MUST take every `cs-image-system` package from
  TestPyPI and every other dependency from PyPI.
- **FR-004** *(dropped 2026-11-24)*: Each family's acceptance tests MUST run against the system's
  newest TestPyPI release inside its ranges, and its oldest-versions leg
  against the oldest its ranges allow.
- **FR-005** *(narrowed 2026-11-24, with T021's drop)*: The probes a
  release runs first (the versions already held, the families released
  elsewhere) MUST read TestPyPI. The isolated runs keep reading PyPI for
  the SDK's published versions and files, so an SDK version TestPyPI
  alone holds counts as unpublished there: it is installed as this
  repository's build, said by name, and the guard against a change
  under a published version sees only the versions on PyPI.
- **FR-006** *(dropped 2026-11-24: final releases only, as before)*: The starter template repositories MUST be pushed for each
  release.
- **FR-007** *(narrowed 2026-11-24: one statement in the operations guide)*: Every document in the three repositories and the starters
  that says how to install MUST say how to install a TestPyPI release, and
  MUST link one statement of TestPyPI's limits.
- **FR-008**: Lifting the decision at 1.0 MUST be one named change per
  repository, said in the documents.
- **FR-009**: This repository's publishing MUST reach TestPyPI by trusted
  publishing, as the two families do: a pushed tag publishes every one of
  its packages, with no upload token stored in the repository or its
  secrets, and the setup for each project on TestPyPI is written down for
  a maintainer and a fork.

### Key Entities

- **The standing decision**: TestPyPI only until 1.0, the operator's to
  lift.
- **The system's own packages**: every distribution named
  `cs-image-system` or `cs-image-system-*`, from this repository or a
  family's.
- **A consumer**: anything that installs or locks the system's packages.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero versions are added to PyPI for any of the system's
  packages until 1.0.
- **SC-002**: Every interim release runs the lighter check, and every
  release whose changes touch what only the full proof exercises is
  flagged before it runs, in 100% of releases.
- **SC-003**: After a release, the reference configuration, a clean
  install and every repository's lock name that release, with zero
  third-party packages taken from TestPyPI.
- **SC-004** *(dropped 2026-11-24)*: Each family's tests run against the system's newest release
  in 100% of their runs.
- **SC-005** *(dropped 2026-11-24)*: Every install line in the documents installs the newest
  release when followed on a clean machine.

## Assumptions

- The two families already publish by trusted publishing to TestPyPI and
  PyPI (their specification 001 and spec 010's T050); only their PyPI step
  changes.
- PyPI's existing versions stay; nothing is yanked or deleted there.
- The release that carries this specification is the next release, the
  batched one for specifications 002, 003 and 006, together with spec
  010's; this specification lands first, since that release is its first
  TestPyPI-only one.
- Versions move only their third number (the second standing decision);
  this specification changes no version rule.
