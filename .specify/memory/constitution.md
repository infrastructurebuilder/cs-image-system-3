<!--
Sync Impact Report (scratch for review; remove before committing)

Version change: none -> 1.0.0 (first ratified constitution)
Modified principles: none (first version)
Added sections: Users; Core Principles I-X; Additional Constraints;
  Development Workflow; Governance
Removed sections: none
Source of each principle:
  III, IV, V and the first half of VI restate invariants the system
  already keeps (dry run and the plan gate; the golden; public-safety;
  the import direction). I, II, VII, VIII, IX, X and the second half of
  VI are new, from the examination of 2026-11-16.
Supersedes: the "Standing decisions" block of the retired work list.
Templates: plan, spec and tasks templates read this file at run time and
  were not modified.
Deferred items: none.
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
  runs before a release.
- Python runs through `uv run python`.
- Live testing uses the `cs-image-system-testconfig` repository as its
  configuration. Fast and local tests use the fixtures.
- Google Cloud spending is the operator's own money. No GCE cycle runs
  unless a change could break the Google Cloud code, and whatever it
  stands up is torn down.

## Development Workflow

- Work is specified with Spec Kit: a specification (what and why, for a
  named user), then a plan, tasks, implementation and convergence.
- A specification describes changes only. The existing system is
  specified by its golden and its tests, not retroactively.
- One feature branch per specification, `feature/<name>` from `develop`,
  finished by a squash-merge with the branch kept. Nothing is committed
  to `main` directly. Nothing is committed or pushed unless the operator
  asks.
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

**Version**: 1.0.0 | **Ratified**: 2026-11-16 | **Last Amended**: 2026-11-16
