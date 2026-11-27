<!--
Sync Impact Report (scratch for review; remove before committing)

Version change: 1.2.0 -> 1.3.0
Bump: MINOR. One constraint of a section changed in substance, which is
  more than wording (PATCH) and touches no principle (MAJOR is for a
  principle removed or redefined); Governance gives MINOR to a section
  "materially expanded", the nearest case.
Amended: 2026-11-27, by the operator ("amend the constitution for the
  lighter check").
Modified principles: none
Added sections: none
Changed sections: Additional Constraints, its first bullet. It said
  "`just full-test` runs before a release." Since the operator's decision
  of 2026-11-23 (specification 013, FR-002 and FR-002a) an interim
  release until 1.0 is gated by the lighter check, runs the full proof
  only when asked with `--full`, and says before it starts when the full
  proof is probably needed. The bullet now says so.
Removed sections: none
Templates: plan, spec and tasks templates read this file at run time and
  were not modified.
Deferred items: none. The guides that repeated the old sentence are
  corrected by specification 013's T078 (outside this file).

Earlier amendments:
  1.1.0 -> 1.2.0 (2026-11-21): Development Workflow gained one bullet:
    the definition of done for a specification (six conditions, each
    shown by a command or a record), the states "in progress" and
    "merged", and its reach: every specification, those written before
    it included.
  1.0.0 -> 1.1.0 (2026-11-17): Additional Constraints gained the Azure
    cloud testing constraint (the operator's cost; whatever is created
    is torn down).
  none -> 1.0.0 (2026-11-16): first ratified constitution. Sections
    Users; Core Principles I-X; Additional Constraints; Development
    Workflow; Governance. III, IV, V and the first half of VI restate
    invariants the system already keeps; I, II, VII, VIII, IX, X and
    the second half of VI are new, from the examination of 2026-11-16.
    Supersedes the "Standing decisions" block of the retired work list.
-->

# cs-image-system Constitution

## Users

Every specification names which of these it serves.

- **Modellers and scientists** log into instances built from released
  images and run models. They never touch the configuration.
- **Operators** help modellers by adding and changing entries (images,
  instances, storages, groups) and keep the system running through its CI.
- **An adopting team** starts a configuration repository from a starter
  and runs the system itself.
- **A plugin author** writes or owns a provider or identity plugin
  against the published kit.

## Core Principles

### I. Purpose first

The system exists to deliver machine images that are correct for a given
HPC model and formally released. Every specification MUST name the user
it serves from the list above. Work that serves none of them MUST state
its reason in its specification.

Rationale: the platform's mechanisms were built and proven long before
its first real payload; a named user keeps work pointed at the payload.

### II. Acceptance is executable

Every specification MUST end in a command or CI job that passes or
fails. A review, a reading or a document is not acceptance. A skipped
check is a failed check: no gate may report success when a leg it
depends on did not run.

Rationale: progress measured by fresh reviews produced the same report
twice; a gate that skipped and passed let a release through unproven.

### III. Nothing irreversible by default

A run is a dry run unless told otherwise. An apply happens only through
the plan gate, which MUST refuse a plan that destroys anything no
declaration sanctions. The system MUST NOT destroy identities or
access-control groups.

Rationale: the system manages infrastructure that can destroy money and
data.

### IV. The emission is the contract with the past

Generated output for the frozen fixture MUST be byte-identical to the
golden unless the change says it moves. A moved golden MUST be read
file by file, never accepted wholesale.

Rationale: the system is a compiler; its output is its behaviour.

### V. Public by construction

Everything the system reads from or writes to a configuration repository
MUST be safe for the open internet. A secret stays ciphertext in every
emitted artifact. The public-safety gate MUST run as a pre-commit hook
and in CI.

Rationale: configuration repositories are public by design.

### VI. Layers point one way and plugins do not interfere

Dependencies run contract, then kit, then engine, then CLI, and never
back. A plugin MUST NOT import the engine or another provider's plugin.
The kit (`cs-image-system-base`) is the SDK a plugin is written against:
it MUST have a declared public surface and its own version. Installing,
loading or testing one plugin MUST NOT change the behaviour of another.

Rationale: one runtime or plugin set must not interfere with another,
at install time, at run time, in tests and in releases alike.

### VII. A budget, and subtraction preferred

Every plan MUST state its expected effect on source lines, workspace
packages, contract protocol members and test count. Growth in any of
them MUST carry a reason written in the plan. Deleting is a first-class
outcome and needs no further justification.

Rationale: a fortnight of fixes grew the source by a sixth and the
tests by a third while aiming to simplify.

### VIII. One source per fact

Counts, recipe lists, field tables and version numbers in documents
MUST be generated from the code or be absent. A fact is stated in one
owning place and linked from the others.

Rationale: hand-kept counts drift with every structural change.

### IX. Tests guard behaviour or architecture

A test MUST NOT assert wording, naming, ordering or the prose of a
document. A test that asserts a property of the repository itself is
allowed only when it holds an architectural invariant of Principle VI
or a safety invariant of Principles III to V.

Rationale: tests of form fail legitimate refactors and catch no defect
a user would meet.

### X. What a change makes false is part of the change

Every plan MUST list the statements elsewhere that the change makes
untrue (documents, starters, comments, the reference configuration),
and the change MUST correct them.

Rationale: each structural fix left stale statements along the seam it
opened.

## Additional Constraints

- The `Justfile` is the single entry point: `init`, `build`, `test`,
  `full-test`, `release`. `just test` is the local acceptance bar; lint,
  the type check (zero errors) and the tests all block. `just full-test`
  runs before a release that is proven in full (`just release ... --full`).
  Until the operator declares 1.0, an interim release is gated by the
  lighter check instead (`just test` and the quickstart page's own
  commands), and MUST say before it starts, without refusing, when the
  full proof is probably needed (specification 013).
- Python runs through `uv run python`.
- Live testing uses the `cs-image-system-testconfig` repository as its
  configuration. Fast and local tests use the fixtures.
- Google Cloud spending is the operator's own money. No GCE cycle runs
  unless a change could break the Google Cloud code, and whatever it
  stands up is torn down.
- Any Azure cloud testing follows the same principle: the operator bears
  the cost.  No Azure cycle runs unless a change could break the
  Azure code, and whatever is created is torn down.

## Development Workflow

- Work is specified with Spec Kit: a specification (what and why, for a
  named user), then a plan, tasks, implementation and convergence.
- A specification describes changes only. The existing system is
  specified by its golden and its tests, not retroactively.
- One feature branch per specification, `feature/<name>` from `develop`,
  finished by a squash-merge with the branch kept. Nothing is committed
  to `main` directly. Nothing is committed or pushed unless the operator
  asks.
- A specification is **done** when all of the following hold, each shown
  by a command or a record, not by a reading:
  1. Every task in its `tasks.md` is checked, and each has a record of
     what was done and the evidence (a commit, a run, a count).
  2. `/speckit-converge` was run after the last implementation and
     appended nothing, or every task it appended is itself done.
  3. The acceptance it ends in (Principle II) was run at the end and
     passed: its quickstart walked step by step, each result recorded.
  4. Its branch is squash-merged into `develop`, the branch kept.
  5. When its plan names a release, that release is published, every
     run it started passed, and the reference configuration has taken
     it with its drift check green. When the plan names none, a release
     that carries the specification is still preferred where one is
     possible; if none is cut, the records say why.
  6. Its `spec.md` status line and its row in `specs/README.md` say
     **complete**, with the date.

  This holds for every specification, those written before it included.
  Until all six hold, a specification is **in progress**; one that is
  merged but not yet done is **merged**. A step that does not apply is
  named as not applying in its tasks' records rather than left out.

  Rationale: a merge proves the code moved, not that the user was served.
  Spec 005 was called complete without convergence, the one step the
  workflow lists that no command enforced.
- A defect that does not block a named user waits until its code is
  touched for another reason. There are no standing hygiene bundles.
- `/ATTIC` holds the retired work ledger, the frozen history and past
  reviews. Nothing there describes the present. No current document or
  specification takes a fact from it. Agents MUST NOT read it for
  guidance, cite it or maintain it unless the operator asks.

## Governance

This constitution supersedes the retired "standing decisions". Where a
current document disagrees with it, the constitution holds and the
document is corrected.

- **Amendment.** The operator amends the constitution. Each amendment
  is recorded with a version bump: MAJOR when a principle is removed or
  redefined, MINOR when a principle or section is added or materially
  expanded, PATCH for wording.
- **Compliance.** Every plan carries a constitution check against
  Principles I to X. A violation MUST be justified in the plan's
  complexity section, or the plan changes.
- **Review.** A specification is reviewed against Principles I and II
  before it is planned: it names its user and ends in an executable
  acceptance.

**Version**: 1.3.0 | **Ratified**: 2026-11-16 | **Last Amended**: 2026-11-27
