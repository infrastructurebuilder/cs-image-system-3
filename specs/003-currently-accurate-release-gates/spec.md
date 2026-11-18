# Feature Specification: Release gates that cannot report a pass they did not earn

**Feature Directory**: `specs/003-honest-release-gates`

**Feature Branch**: `feature/honest-release-gates` (to be created from `develop` when planning starts)

**Created**: 2026-11-16

**Status**: Draft

**Input**: User description: "A release that cannot fool you: a skipped gate fails, the tag is pushed by name, the take waits for the index, a missing CI run is reported at once."

**Users served**: operators (the person cutting a release); an adopting team and a plugin author (they install what a release publishes and must be able to trust it).

## Why

A release is the one moment the system does something that cannot be taken
back: it publishes packages. Its gate exists to make sure everything was
checked first. Today the gate can pass without checking.

- The full test run prints "SKIPPED" for a group of checks whose
  prerequisite is missing (no container daemon, no reference
  configuration, an expired session) and then reports "passed".
- A release probes the operator's sessions before a gate that takes most
  of an hour, and a session lasts an hour. If one expires on the way, the
  checks that need it are skipped and the release goes ahead.
- CI jobs that have no secrets finish green.
- The watcher that follows a release's CI runs reports a run that never
  started only after waiting an hour.

The release of 0.1.10 showed the last of these, and two more faults that
have since been fixed and must stay fixed: the release's own tag is now
pushed by name, and an upgrade now asks the package index afresh.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A release never passes a check that did not run (Priority: P1)

An operator starts a release. Partway through the gate, a prerequisite of
some checks goes away or was never there. The gate stops and says which
checks did not run and why. Nothing is published.

**Why this priority**: this is the fault that can put an unproven release
on the public index. Everything else in this feature is about speed or
convenience; this is about trust.

**Independent Test**: start a release in a rehearsal mode with the
container daemon stopped; the gate fails and names the checks that could
not run. Repeat with a session that expires during the gate; same
outcome. In both cases nothing was uploaded.

**Acceptance Scenarios**:

1. **Given** a release whose gate includes checks that need a container
   daemon, **When** the daemon is not available, **Then** the gate fails,
   names those checks, and nothing is published.
2. **Given** a release whose gate includes checks that need a live
   session, **When** the session is absent or expires before those checks
   run, **Then** the gate fails at those checks, names the session and
   how to renew it, and nothing is published.
3. **Given** a gate in which every required check ran and passed,
   **When** the release proceeds, **Then** its record lists each required
   check with the fact that it ran.
4. **Given** a release, **When** an operator tries to exclude a required
   check, **Then** the release refuses: a release has no optional checks.

---

### User Story 2 - A test run says exactly what it ran (Priority: P2)

A developer runs the full test suite on a machine that lacks something
(no container daemon, no reference configuration beside the checkout).
They can ask for a run without those checks, and the result says plainly
that those checks were excluded at their request. If they did not ask,
the missing checks make the run fail. A run never says "passed" about
checks it did not perform.

**Why this priority**: the release gate is built from this run. If the
run's own verdict is honest, the release gate inherits it.

**Independent Test**: run the full suite with a prerequisite missing and
no exclusion: it fails and names what could not run. Run it again asking
to exclude those checks: it succeeds and its last line names what was
excluded.

**Acceptance Scenarios**:

1. **Given** a missing prerequisite and no exclusion requested, **When**
   the full test run finishes, **Then** it reports failure and lists the
   checks that did not run.
2. **Given** a missing prerequisite and an explicit request to exclude
   the checks that need it, **When** the run finishes, **Then** it
   reports success for what ran and names what was excluded, in its last
   line and in its exit status' meaning.
3. **Given** any full test run, **When** it finishes, **Then** its
   summary gives three counts: checks run, checks excluded on request,
   checks failed.
4. **Given** a CI job that could not perform its steps (it has no
   secrets, for example), **When** it finishes, **Then** it is not shown
   as a success.

---

### User Story 3 - A missing CI run is reported in minutes (Priority: P3)

An operator runs the watcher after a release. One of the CI runs the
release should have started does not exist. The watcher says so within
minutes, names the run and gives the command that starts it, instead of
waiting out its full timeout.

**Why this priority**: in the release of 0.1.10 this cost an hour and the
publishing of the starter repositories waited on a person noticing.

**Independent Test**: point the watcher at a commit for which the branch
runs exist and the tag's run does not. It reports the tag's run as never
started within five minutes and prints the remedy.

**Acceptance Scenarios**:

1. **Given** a release commit for which some expected runs exist and one
   does not, **When** the watcher has seen the others start, **Then**
   within five minutes it reports the missing run as never started and
   names how to start it.
2. **Given** all expected runs exist, **When** the watcher finishes,
   **Then** it gives one verdict per run as it does today.
3. **Given** the watcher cannot reach the CI service on one look,
   **When** it looks again, **Then** it carries on (the behaviour fixed
   after 0.1.10 holds).

---

### User Story 4 - Nothing irreversible happens on stale information (Priority: P4)

A release's gate takes most of an hour. Before the release uploads
anything, it confirms again the things it checked at the start that can
change in an hour: that the remote has no new commits, and that the
sessions it will still need are alive.

**Why this priority**: today only the package index is asked again. The
window is long enough for the other facts to change.

**Independent Test**: in a rehearsal, add a commit to the remote during
the gate; the release stops before uploading and says the remote moved.

**Acceptance Scenarios**:

1. **Given** the remote gained a commit during the gate, **When** the
   gate ends, **Then** the release stops before any upload, says so, and
   leaves the checkout where it started.
2. **Given** a session the remaining steps need has expired during the
   gate, **When** the gate ends, **Then** the release stops before any
   upload and names the session.

---

### User Story 5 - Publishing can be finished after a partial failure (Priority: P5)

A release publishes to several places in sequence: the package index, the
reference configuration, the starter repositories. If one step fails
partway, the operator runs one command that completes what is missing
and leaves alone what is already done.

**Why this priority**: the package upload already resumes. Publishing the
starter repositories does not: a second attempt stops at the first
repository that already has the tag.

**Independent Test**: in a rehearsal, publish to two of the starter
repositories, then stop. Run the publishing step again: it completes the
rest and reports the two as already done.

**Acceptance Scenarios**:

1. **Given** some starter repositories already carry the release's tag
   and others do not, **When** publishing is run again, **Then** it
   publishes to the others and reports the first group as already done.
2. **Given** a release whose upload succeeded and whose push of the
   branch was refused, **When** the operator runs the finishing command,
   **Then** it completes the push and what follows it.

---

### Edge Cases

- A developer has no container daemon by choice and wants a quick local
  run: the exclusion must be easy to ask for and impossible to get by
  accident.
- A pull request from a fork has no secrets by design. Its job must be
  shown as "not run", distinct from both success and failure, and must
  not block the pull request.
- The reference configuration is not checked out beside the system. For
  a developer that is an exclusion; for a release it is a failure.
- A check is slow and the session expires while it is running, not
  before it starts.
- The watcher is started before the release has pushed anything.
- Two releases are attempted from two machines at once.
- A step that was fixed after 0.1.10 regresses: several tags pushed at
  once, or an upgrade answered from a stale index.

## Requirements *(mandatory)*

### Functional Requirements

**Honest verdicts**

- **FR-001**: A test run MUST NOT report success for a check it did not
  perform.
- **FR-002**: A check that cannot run because a prerequisite is missing
  MUST make the run fail, unless the caller explicitly asked to exclude
  it.
- **FR-003**: An exclusion MUST be requested by name by the caller. No
  environment condition may cause one implicitly.
- **FR-004**: Every full test run MUST end with a summary of checks run,
  checks excluded on request and checks failed, and a result that
  distinguishes "all required checks passed" from "passed with
  exclusions".
- **FR-005**: A CI job that did not perform its steps MUST NOT be shown
  as a success. On a pull request from a fork it MUST be shown as not
  run, without blocking.

**The release gate**

- **FR-006**: A release MUST NOT accept exclusions. Every check its
  target requires either runs and passes or the release stops.
- **FR-007**: When a check in a release's gate cannot run, the release
  MUST stop before anything is published, name the check and the cause,
  and leave the checkout as it found it.
- **FR-008**: A release's record MUST list each required check and that
  it ran.
- **FR-009**: After the gate and before the first upload, a release MUST
  confirm again that the remote has not moved and that every session a
  remaining step needs is alive, and stop if either fails.

**The watcher**

- **FR-010**: When an expected CI run for a release commit does not
  exist, the watcher MUST report it as never started within five minutes
  of the other runs for that commit having started, and MUST print the
  command that starts it.
- **FR-011**: The watcher MUST accept a run started by hand for the same
  commit and reference as the expected run.

**Resuming**

- **FR-012**: Publishing to the starter repositories MUST be repeatable:
  a repository that already carries the release's tag is reported as
  done and skipped, and the rest are published.
- **FR-013**: One finishing command MUST complete a release from any
  state after a successful upload, including a refused push.

**What must stay fixed**

- **FR-014**: A release MUST push its own tag by name and no other tag.
- **FR-015**: Installing a just-published release in an upgrade MUST ask
  the package index afresh.

**Proportion**

- **FR-016**: This feature MUST NOT add to the number of release
  scripts, and its plan MUST state its effect on the size of the release
  tooling and its tests (Constitution VII). Simplifying is preferred to
  adding cases.
- **FR-017**: The statements in the manuals that this feature makes
  false (what the full test run does when a prerequisite is absent; what
  a skipped leg means) MUST be corrected in the same work.

### Key Entities

- **Check (leg)**: one named part of the full test run, with its
  prerequisites.
- **Exclusion**: a caller's explicit request to leave a named check out
  of one run.
- **Gate**: the set of checks a release target requires, with no
  exclusions allowed.
- **Run summary**: the counts of checks run, excluded and failed, and the
  overall result.
- **Expected run**: a CI run that a release should have started, for a
  given commit and reference.
- **Release record**: what a release writes down about itself, including
  the checks that ran.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a rehearsal with the container daemon stopped, a release
  stops at its gate, names the checks that could not run, and publishes
  nothing; the same with a session that expires during the gate.
- **SC-002**: Zero ways remain for the full test run to print "passed"
  when a check was neither performed nor excluded by name.
- **SC-003**: Every full test run ends with the three counts, and its
  result distinguishes a complete pass from a pass with exclusions.
- **SC-004**: A missing expected run is reported within 5 minutes, down
  from 60.
- **SC-005**: A remote that moved during the gate stops a rehearsed
  release before any upload.
- **SC-006**: Publishing to the starter repositories completes on a
  second attempt after a partial first attempt, with no cleanup by hand.
- **SC-007**: The release tooling and its tests are no larger after this
  feature than before it.
- **SC-008**: The next real release after this feature completes its walk
  with no step done by hand that the walk did not plan for.

## Assumptions

- "A rehearsal" is a way to run a release against a test index and
  scratch repositories so that the scenarios above can be exercised
  without publishing. If no such mode exists, providing one is part of
  this feature, because the acceptance tests need it.
- The two fixes made after 0.1.10 (the tag pushed by name; the index
  asked afresh) are in the tree; this feature keeps them and does not
  redo them.
- Running a release entirely from CI, replacing long-lived tokens with
  trusted publishing, and reducing the number of published packages are
  out of scope. Each would shrink the release further and deserves its
  own specification.
- The reference configuration remains a sibling checkout for now. This
  feature makes its absence explicit; it does not remove the dependency.
- A developer's quick local run with exclusions stays possible; only the
  silence is removed.
- Which checks a development release requires and which a final release
  requires stay as they are today.
